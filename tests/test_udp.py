"""Loopback UDP tests: registration, commands, routing and recovery."""

import asyncio
from collections.abc import AsyncIterator
import logging
from unittest.mock import Mock, patch

import pytest

from besen.exceptions import CannotConnect, CommandFailed, InvalidAuth
from besen.protocol import ParsedPacket, build_command, parse_packet
from besen.udp import BesenUdpClient, BesenUdpHub

SERIAL = "8949281891483449"
SERIAL_INT = int.from_bytes(bytes.fromhex(SERIAL), "little")


def reply(command: int, data: bytes = b"", *, serial: int = SERIAL_INT) -> bytes:
    return build_command(serial, "123456", command, [data])


def login_data() -> bytes:
    data = bytearray(69)
    data[0] = 10
    data[1:6] = b"Besen"
    data[17:21] = b"BS20"
    data[53] = 32
    return bytes(data)


class Charger(asyncio.DatagramProtocol):
    """A real local socket that answers the protocol, without real hardware."""

    def __init__(self) -> None:
        self.transport: asyncio.DatagramTransport
        self.requests: list[ParsedPacket] = []
        self.reject = False
        self.silent = False
        self.got_start = asyncio.Event()
        self.temperature_requests = 0
        self.drop_first_temperature_reply = False
        self.drop_status = False

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        request = parse_packet(data)
        self.requests.append(request)
        if self.silent:
            return
        if request.command == 0x8002:
            self.transport.sendto(
                reply(341) if self.reject else reply(2, login_data()), addr
            )
        elif request.command == 0x8001:
            # Observed on the physical BS20 immediately after login confirm.
            self.transport.sendto(reply(1, login_data()), addr)
            self.transport.sendto(reply(3), addr)
        elif request.command == 0x800D:
            if self.drop_status:
                return
            status = bytearray(25)
            status[0], status[18], status[20] = 1, 4, 12
            self.transport.sendto(reply(13, bytes(status)), addr)
        elif request.command == 0x8107:
            self.transport.sendto(reply(263, b"\x02\x10"), addr)
        elif request.command == 0x8112:
            self.temperature_requests += 1
            if not self.drop_first_temperature_reply or self.temperature_requests > 1:
                self.transport.sendto(reply(274, b"\x02\x01"), addr)
        elif request.command == 0x8007:
            self.got_start.set()
            self.transport.sendto(reply(7, b"\x01\x00\x01\x00\x10"), addr)


@pytest.fixture
async def lan() -> AsyncIterator[tuple[BesenUdpHub, BesenUdpClient, Charger]]:
    transport, charger = await asyncio.get_running_loop().create_datagram_endpoint(
        Charger, local_addr=("127.0.0.1", 0)
    )
    host, port = transport.get_extra_info("sockname")[:2]
    hub = BesenUdpHub(port=0, bind="127.0.0.1")
    hub.discovered[SERIAL] = (host, port)
    client = BesenUdpClient(
        address="old-ble-id",
        pin="123456",
        hub=hub,
        host=host,
        serial=SERIAL,
        logger=logging.getLogger(__name__),
        sync_clock=False,
    )
    try:
        yield hub, client, charger
    finally:
        await client.async_stop()
        await hub.async_stop()
        transport.close()


async def test_live_udp_login_and_charge_acknowledgement(
    lan: tuple[BesenUdpHub, BesenUdpClient, Charger],
) -> None:
    """A wire-order serial, learned port and correlated ack control one charger."""
    hub, client, charger = lan
    await client.async_start()
    await client.async_wait_for_status()
    assert client.state.authenticated and client.state.available
    assert client.address == "old-ble-id"
    assert client.state.info.model == "BS20"
    assert charger.requests[0].identifier == SERIAL
    assert charger.requests[0].password == b"123456"
    await client.async_start_charging(16)
    await client.async_wait_for_heartbeat()
    assert charger.got_start.is_set()
    commands = [packet.command for packet in charger.requests]
    assert 0x8001 in commands
    assert 0x8008 not in commands
    assert client.state.config.charge_amps == 16
    await client.async_stop()
    assert client not in hub.clients and not client.is_connected
    with pytest.raises(CommandFailed, match="not authenticated"):
        await client.async_set_charge_amps(10)


async def test_udp_session_record_push(
    lan: tuple[BesenUdpHub, BesenUdpClient, Charger],
) -> None:
    """Session metadata reaches listeners through the existing LAN route."""

    hub, client, charger = lan
    await client.async_start()
    await client.async_wait_for_status()
    assert hub.transport is not None
    destination = hub.transport.get_extra_info("sockname")
    payload = bytearray(95)
    payload[0] = 1
    payload[1:17] = b"client-A".ljust(16, b"\x00")
    payload[17:33] = b"Key".ljust(16, b" ")
    payload[33:49] = b"2026102512001337"
    payload[58] = 24
    payload[64:68] = (1_792_929_602).to_bytes(4, "big")
    payload[68:72] = (1_792_929_608).to_bytes(4, "big")
    received = asyncio.Event()
    client.add_listener(lambda state: received.set() if state.last_session else None)
    charger.transport.sendto(reply(9, bytes(payload)), destination)
    await asyncio.wait_for(received.wait(), 1)
    assert client.state.last_session is not None
    assert client.state.last_session.stopped_by == "Key"
    assert client.state.last_session.stop_reason_code == 24


async def test_rejected_pin_is_distinct_from_timeout(
    lan: tuple[BesenUdpHub, BesenUdpClient, Charger],
) -> None:
    hub, client, charger = lan
    charger.reject = True
    with pytest.raises(InvalidAuth):
        await client.async_start()
    assert bool(client.state.auth_failed)
    assert client not in hub.clients
    charger.reject = False
    charger.silent = True
    with (
        patch("besen.udp.LOGIN_INTERVAL", 0.01),
        pytest.raises(CannotConnect, match="Timed out"),
    ):
        await client.async_start()
    assert not client.state.auth_failed
    assert not client.state.available


async def test_routing_rejects_foreign_serial_and_tracks_dhcp(
    lan: tuple[BesenUdpHub, BesenUdpClient, Charger],
) -> None:
    hub, client, _charger = lan
    await client.async_start()
    old_host = client.host
    hub.receive(b"invalid", ("192.0.2.2", 1))
    hub.receive(reply(3, serial=0), ("192.0.2.2", 1))
    hub.receive(reply(3, serial=123), (old_host or "127.0.0.1", 2))
    assert client.host == old_host
    hub.receive(reply(3), ("127.0.0.2", 12345))
    assert client.host == "127.0.0.2" and client.port == 12345
    await client.async_stop()
    client.receive(parse_packet(reply(3)), ("127.0.0.3", 3))
    assert client.host == "127.0.0.2"


async def test_single_registration_and_probe_privacy(
    lan: tuple[BesenUdpHub, BesenUdpClient, Charger],
) -> None:
    hub, client, _charger = lan
    await client.async_start()
    other = BesenUdpClient(
        address="duplicate",
        pin="654321",
        hub=hub,
        host=client.host,
        serial=SERIAL,
        logger=logging.getLogger(__name__),
    )
    with pytest.raises(CannotConnect, match="already"):
        await other.async_start()
    assert client.is_connected
    send = Mock()
    with patch.object(hub, "send", send):
        hub.probe()
    probe = parse_packet(send.call_args.args[0])
    assert probe.password == b"\0" * 6
    assert probe.identifier == "0000000000000000"


async def test_registration_expires_despite_command_replies(
    lan: tuple[BesenUdpHub, BesenUdpClient, Charger],
) -> None:
    _hub, client, _charger = lan
    await client.async_start()
    reconnect = Mock()
    client._last_heading = 0
    with (
        patch.object(client, "_schedule_reconnect", reconnect),
        patch("besen.udp.HEARTBEAT_TIMEOUT", 0),
        patch("besen.udp.asyncio.sleep", new=AsyncSleepOnce(client)),
    ):
        await client._watchdog_loop()
    assert not client.state.available and not client.state.authenticated
    assert not client.state.auth_failed
    reconnect.assert_called_once()
    with pytest.raises(CommandFailed, match="not authenticated"):
        await client.async_stop_charging()


class AsyncSleepOnce:
    """Stop the watchdog after its first deterministic iteration."""

    def __init__(self, client: BesenUdpClient) -> None:
        self.client = client

    async def __call__(self, seconds: float) -> None:
        self.client._stopping = True


async def test_announcements_and_status_acknowledgements(
    lan: tuple[BesenUdpHub, BesenUdpClient, Charger],
) -> None:
    _hub, client, _charger = lan
    await client.async_start()
    await client.async_wait_for_heartbeat()
    with patch.object(client, "_send_command", autospec=True) as send:
        await client._async_handle_packet(4, bytes(25), SERIAL)
        await client._async_handle_packet(5, bytes(80), SERIAL)
        assert [call.args[0] for call in send.await_args_list] == [0x8004, 0x8005]
    last_heading = client._last_heading
    with patch.object(client, "_schedule_reconnect") as reconnect:
        await client._async_handle_packet(1, login_data(), SERIAL)
    reconnect.assert_not_called()
    assert client.state.authenticated
    assert client._last_heading == last_heading
    await client.async_wait_for_heartbeat()
    client._heading_received.clear()
    with pytest.raises(TimeoutError):
        await client.async_wait_for_heartbeat(0.01)
    client._heading_received.set()
    client._set_state(authenticated=False)
    with pytest.raises(CannotConnect, match="no longer active"):
        await client.async_wait_for_heartbeat()


async def test_missing_temperature_reply_recovers_on_heartbeat(
    lan: tuple[BesenUdpHub, BesenUdpClient, Charger],
) -> None:
    _hub, client, charger = lan
    charger.drop_first_temperature_reply = True
    ready = asyncio.Event()
    remove = client.add_listener(
        lambda data: ready.set() if data.config.temperature_unit == "Celsius" else None
    )
    try:
        await client.async_start()
        async with asyncio.timeout(1):
            await ready.wait()
        assert client.state.authenticated
        assert client.state.config.temperature_unit == "Celsius"
        assert charger.temperature_requests >= 2
    finally:
        remove()


async def test_fresh_status_is_required_after_every_login(
    lan: tuple[BesenUdpHub, BesenUdpClient, Charger],
) -> None:
    hub, client, charger = lan
    with pytest.raises(TimeoutError):
        await client.async_wait_for_status(0.01)
    await client.async_start()
    await client.async_wait_for_status()
    assert SERIAL in hub.last_seen
    client._set_state(authenticated=False)
    with pytest.raises(CannotConnect, match="no longer active"):
        await client.async_wait_for_status()
    await client.async_stop()
    charger.drop_status = True
    await client.async_start()
    assert client.state.charge.current_state is not None  # Retained cached data.
    with pytest.raises(TimeoutError):
        await client.async_wait_for_status(0.01)


async def test_wifi_credentials_are_never_sent_over_udp(
    lan: tuple[BesenUdpHub, BesenUdpClient, Charger],
) -> None:
    hub, client, charger = lan
    await client.async_start()
    with patch.object(hub, "send", wraps=hub.send) as send:
        with pytest.raises(CommandFailed, match="requires a Bluetooth connection"):
            await client.async_configure_wifi("private-network", "private-password")
        send.assert_not_called()
    await asyncio.sleep(0)
    assert client.wifi_acknowledgement is None
    assert all(packet.command != 0x810A for packet in charger.requests)


async def test_unknown_serial_host_login_and_socket_rebind(
    lan: tuple[BesenUdpHub, BesenUdpClient, Charger],
) -> None:
    hub, client, _charger = lan
    client._update_info(serial=None)
    client.port = hub.discovered[SERIAL][1]
    await client.async_start()
    assert client.state.info.serial == SERIAL
    assert client.is_connected
    await hub.async_stop()
    assert hub.transport is None
    with pytest.raises(CommandFailed, match="closed"):
        hub.probe()
    await hub.async_start()
    await hub.async_start()


async def test_bind_resolution_and_serial_errors() -> None:
    with pytest.raises(ValueError):
        BesenUdpClient(
            address="x",
            pin="123456",
            hub=BesenUdpHub(port=0),
            logger=logging.getLogger(__name__),
            serial="bad",
        )
    hub = BesenUdpHub(port=0, bind="not-an-address.invalid")
    with pytest.raises(CannotConnect, match="bind"):
        await hub.async_start()
    hub = BesenUdpHub(port=0, bind="127.0.0.1")
    client = BesenUdpClient(
        address="x",
        pin="123456",
        hub=hub,
        logger=logging.getLogger(__name__),
        host="not-an-address.invalid",
    )
    try:
        with pytest.raises(CannotConnect, match="resolve"):
            await client.async_start()
    finally:
        await hub.async_stop()
