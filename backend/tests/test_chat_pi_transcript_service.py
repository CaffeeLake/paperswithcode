import pytest

from backend.services.chat_pi_transcript_service import (
    PiTranscriptError,
    _database_entry,
    _envelope,
    _native_entry,
    _serialized,
)


def test_pi_session_header_is_not_indexed_as_a_tree_entry():
    header = {
        "type": "session",
        "id": "00000000-0000-4000-8000-000000000001",
        "version": 3,
    }

    assert _envelope(header) == (None, None, "session")
    assert _serialized(header)[1] > 2


def test_pi_transcript_envelope_preserves_native_tree_ids():
    assert _envelope({"type": "message", "id": "child", "parentId": "parent"}) == (
        "child",
        "parent",
        "message",
    )


@pytest.mark.parametrize(
    "entry",
    [
        {"type": "message", "id": ""},
        {"type": "message", "id": "child", "parentId": ""},
        {"type": ""},
    ],
)
def test_pi_transcript_rejects_invalid_native_envelopes(entry):
    with pytest.raises(PiTranscriptError):
        _envelope(entry)


def test_pi_transcript_storage_envelope_round_trips_postgres_forbidden_nul():
    native = {"type": "message", "id": "entry", "content": "a\x00b"}

    stored = _database_entry(native)

    assert "\x00" not in str(stored)
    assert _native_entry(stored) == native
