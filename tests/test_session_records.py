"""Session identity and end-record regressions, with synthetic protocol data.

Offsets were checked against EVSEMaster 3.1.38's currentChargeRecord and the
documented record layout. These fixtures are not physical charger captures.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
import logging
import struct
from unittest.mock import AsyncMock, patch

import pytest

from besen import SessionRecord
from besen.client import BesenClient
from besen.const import STOP_REASON
from besen.exceptions import ProtocolError
from besen.models import BesenData, ChargeStatus, CommandResult
from besen.protocol import PARSERS, parse_session_record

SESSION_ID = b"2026102512001337"
START = 1_792_929_602
END = START + 6


def record_payload(*, reason: int = 24, start: int = START, end: int = END) -> bytes:
    """Build the identity and timing prefix, with unrelated fields as padding."""

    payload = bytearray(95)
    payload[0] = 1
    payload[1:17] = b"client-A".ljust(16, b"\x00")
    payload[17:33] = b"Key".ljust(16, b" ")
    payload[33:49] = SESSION_ID
    payload[58] = reason
    struct.pack_into(">II", payload, 64, start, end)
    return bytes(payload)


@pytest.mark.parametrize("command", [5, 6])
def test_session_report_identity(command: int) -> None:
    """Both report variants expose identifiers without changing telemetry."""

    payload = bytearray(74)
    payload[2:18] = SESSION_ID
    payload[30:46] = b"client-A".ljust(16, b"\x00")
    values = PARSERS[command](bytes(payload), "")
    assert values["session_id"] == SESSION_ID.decode()
    assert values["session_started_by"] == "client-A"
    assert values["session_energy"] == 0.0


@pytest.mark.parametrize("padding", [b"\x00", b"\xff", b" ", b"\x00\xff "])
def test_unset_and_padded_identifiers(padding: bytes) -> None:
    """Padding is not an identity, including mixed firmware sentinels."""

    payload = bytearray(74)
    payload[2:18] = (padding * 16)[:16]
    payload[30:46] = b"Key" + (padding * 13)[:13]
    values = PARSERS[5](bytes(payload), "")
    assert values["session_id"] is None
    assert values["session_started_by"] == "Key"


@pytest.mark.parametrize("reason", [0, 1, 11, 13, 17, 24, 99, 255])
@pytest.mark.parametrize("extra", [0, 51])
def test_session_end_fields(reason: int, extra: int) -> None:
    """Read identities, UTC times and raw reasons, accepting tail extensions."""

    payload = record_payload(reason=reason) + b"\xff" * extra
    record = SessionRecord(**PARSERS[9](payload, ""))
    assert record == SessionRecord(
        line_id=1,
        session_id=SESSION_ID.decode(),
        started_by="client-A",
        stopped_by="Key",
        started_at=datetime.fromtimestamp(START, UTC),
        ended_at=datetime.fromtimestamp(END, UTC),
        stop_reason_code=reason,
        stop_reason=STOP_REASON.get(reason, f"Unknown {reason}"),
    )
    with pytest.raises(FrozenInstanceError):
        record.session_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("timestamp", [0, 0xFFFFFFFF])
def test_unset_record_fields(timestamp: int) -> None:
    """Unset identities and times remain unknown instead of made-up values."""

    payload = bytearray(record_payload(start=timestamp, end=timestamp))
    payload[1:49] = b"\xff" * 48
    values = parse_session_record(bytes(payload), "")
    for key in ("session_id", "started_by", "stopped_by", "started_at", "ended_at"):
        assert values[key] is None


@pytest.mark.parametrize("length", [0, 17, 33, 49, 58, 59, 64, 67, 71])
def test_incomplete_record_rejected(length: int) -> None:
    """Require the full supported prefix, including both timestamps."""

    with pytest.raises(ProtocolError, match="shorter than 72 bytes"):
        parse_session_record(record_payload()[:length], "")


def test_record_minimum_prefix() -> None:
    """Optional fee and log fields are not required for session metadata."""

    assert parse_session_record(record_payload()[:72], "")["stop_reason_code"] == 24


async def test_client_distinguishes_reused_ids_and_filters_retransmissions() -> None:
    """Two sessions in one minute survive duplicate and interleaved reports."""

    client = BesenClient(
        address="AA:BB:CC:DD:EE:FF",
        pin="123456",
        ble_device_provider=lambda: None,
        logger=logging.getLogger(__name__),
    )
    charge = ChargeStatus(session_energy=4.2, session_duration=60)
    command = CommandResult(command="charge_stop")
    client._state = client.state.updated(
        charge=charge, last_command=command, available=True, authenticated=True
    )
    seen: list[BesenData] = []
    client.add_listener(seen.append)
    first = record_payload()
    second = record_payload(start=START + 20, end=END + 20)

    with patch.object(client, "_send_command", new_callable=AsyncMock) as send:
        for payload in (first, first, second, first, second):
            await client._async_handle_packet(9, payload, "")
        await client._async_handle_packet(9, first[:71], "")
        await client._async_handle_packet(
            9, record_payload(end=END + 40), "", generation=99
        )
        # History replay stays outside this API and must not replace the result.
        await client._async_handle_packet(10, first, "")
        send.assert_not_awaited()

    assert len(seen) == 2
    assert seen[0].last_session != seen[1].last_session
    assert client.state.last_session == seen[-1].last_session
    assert client.state.charge is charge
    assert client.state.last_command is command
    assert client.state.available and client.state.authenticated


async def test_record_cache_is_bounded() -> None:
    """An indefinitely connected charger does not accumulate record history."""

    client = BesenClient(
        address="AA:BB",
        pin="123456",
        ble_device_provider=lambda: None,
        logger=logging.getLogger(__name__),
    )
    for index in range(30):
        await client._async_handle_packet(
            9, record_payload(start=START + index, end=END + index), ""
        )
    assert len(client._session_records) == 16
