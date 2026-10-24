"""Regression tests for session ownership and the end-of-session record.

The payloads were captured from a BS20 (three-phase, 16 A) over BLE. A session
started by this library carries USER_ID ("evseMQTT"); a session started with the
charger's button carries "Key".
"""

import logging

import pytest

from besen.client import BesenClient
from besen.exceptions import ProtocolError
from besen.models import BesenData, SessionRecord
from besen.protocol import PARSERS, parse_session_record

# 0x0005 reports during a session started by the library and by the button.
REPORT_LIBRARY = bytes.fromhex(
    "010e323032363130313131333138313333370101ffffffffffff6acb6260657673654d51"
    "54540000000000000000106acb625f0000000100009d4d00009d4d00000000000000000100"
    "00120000000000"
)
REPORT_BUTTON = bytes.fromhex(
    "010e4b65792020203137393137313336383605010b40ffffffff000000004b6579202020"
    "20202020202020202020106acb61960000000000009d1f00009d1f00000000000000000100"
    "00ff0000000000"
)

# 0x0009 records sent right after a session ended.
RECORD_BUTTON_BUTTON = bytes.fromhex(
    "014b6579202020202020202020202020204b6579202020202020202020202020204b6579"
    "202020313739313731333638360005010b40ffffffff1801000000006acb61966acb61aa00"
    "00001400009d1f00009d4c0000002d000000000100000000" + "ff" * 58
)
RECORD_LIBRARY_LIBRARY = bytes.fromhex(
    "01657673654d5154540000000000000000657673654d5154540000000000000000323032"
    "36313031313133313831333337000101ffffffffffff0b016acb62606acb625f6acb6328"
    "000000c900009d4d00009d4d00000000000000000100000000" + "ff" * 58
)
RECORD_BUTTON_LIBRARY = bytes.fromhex(
    "014b657920202020202020202020202020657673654d5154540000000000000000"
    "4b6579202020313739313732313439360005010b40ffffffff0b01000000006acb80186a"
    "cb80610000004900009e5600009e5600000000000000000100000000" + "ff" * 58
)


@pytest.mark.parametrize("command", [5, 6])
@pytest.mark.parametrize(
    ("report", "session_id", "started_by"),
    [
        (REPORT_LIBRARY, "2026101113181337", "evseMQTT"),
        (REPORT_BUTTON, "Key   1791713686", "Key"),
    ],
)
def test_session_report_names_its_owner(
    command: int, report: bytes, session_id: str, started_by: str
) -> None:
    """Live and completed reports carry the session ID and who started it."""
    values = PARSERS[command](report, "")
    assert values["session_id"] == session_id
    assert values["session_started_by"] == started_by


def test_unset_session_owner_is_unknown() -> None:
    """Zero and all-ones padding mean no session, not an empty or garbled name."""
    payload = bytearray(74)
    payload[30:46] = b"\xff" * 16
    values = PARSERS[5](bytes(payload), "")
    assert values["session_id"] is None
    assert values["session_started_by"] is None


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (
            RECORD_BUTTON_BUTTON,
            SessionRecord("Key   1791713686", "Key", "Key", 24, "Key end"),
        ),
        (
            RECORD_LIBRARY_LIBRARY,
            SessionRecord("2026101113181337", "evseMQTT", "evseMQTT", 11, "App stop"),
        ),
        (
            RECORD_BUTTON_LIBRARY,
            SessionRecord("Key   1791721496", "Key", "evseMQTT", 11, "App stop"),
        ),
    ],
)
def test_session_record(record: bytes, expected: SessionRecord) -> None:
    """The record says who started and who stopped the session, and why."""
    assert SessionRecord(**PARSERS[9](record, "")) == expected


def test_session_record_keeps_unknown_stop_reasons() -> None:
    """An unmapped stop reason is reported by code instead of being dropped."""
    payload = bytearray(RECORD_BUTTON_BUTTON)
    payload[58] = 99
    values = parse_session_record(bytes(payload), "")
    assert values["stop_reason_code"] == 99
    assert values["stop_reason"] == "Unknown 99"


def test_session_record_rejects_truncation() -> None:
    """A record too short to hold the stop reason is not guessed at."""
    with pytest.raises(ProtocolError, match="shorter than 59 bytes"):
        parse_session_record(RECORD_BUTTON_BUTTON[:58], "")


@pytest.mark.asyncio
async def test_client_reports_a_repeated_record_once() -> None:
    """The charger sends the record a few times; listeners see it once."""
    client = BesenClient(
        address="AA:BB:CC:DD:EE:FF",
        pin="123456",
        ble_device_provider=lambda: None,
        logger=logging.getLogger(__name__),
    )
    seen: list[BesenData] = []
    client.add_listener(seen.append)

    for _ in range(3):
        await client._async_handle_packet(9, RECORD_BUTTON_BUTTON, "")
    await client._async_handle_packet(9, RECORD_BUTTON_LIBRARY, "")

    assert [state.last_session for state in seen] == [
        SessionRecord("Key   1791713686", "Key", "Key", 24, "Key end"),
        SessionRecord("Key   1791721496", "Key", "evseMQTT", 11, "App stop"),
    ]
    assert client.state.last_session == seen[-1].last_session
