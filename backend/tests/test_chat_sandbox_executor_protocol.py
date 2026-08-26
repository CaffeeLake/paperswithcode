import pytest

from backend.chat_sandbox_worker.executor_protocol import (
    MAX_COMMAND_BYTES,
    MAX_FRAME_BYTES,
    MAX_OFFSET,
    MAX_OUTPUT_CHUNK_BYTES,
    MAX_PATH_BYTES,
    MAX_READ_BYTES,
    MAX_TIMEOUT_MS,
    MAX_TOOL_CALL_ID_BYTES,
    PROTOCOL,
    ProtocolError,
    ResponseSequenceValidator,
    decode_request,
    decode_response,
    encode_request,
    encode_response,
    validate_response_sequence,
)


def test_request_and_response_known_literals_round_trip() -> None:
    request = {
        "protocol": "sandbox-executor-v1",
        "type": "exec",
        "request_id": "request-7",
        "execution_id": "execution-9",
        "tool_call_id": "toolu_01ABC",
        "workspace_id": "workspace-2",
        "command": "printf 'héllo'",
        "timeout_ms": 30_000,
    }
    request_wire = (
        b'{"protocol":"sandbox-executor-v1","type":"exec",'
        b'"request_id":"request-7","execution_id":"execution-9",'
        b'"tool_call_id":"toolu_01ABC","workspace_id":"workspace-2",'
        b'"command":"printf \'h\xc3\xa9llo\'","timeout_ms":30000}\n'
    )
    response = {
        "protocol": "sandbox-executor-v1",
        "type": "output",
        "request_id": "request-7",
        "execution_id": "execution-9",
        "sequence": 1,
        "stream": "stdout",
        "data": "héllo",
    }
    response_wire = (
        b'{"protocol":"sandbox-executor-v1","type":"output",'
        b'"request_id":"request-7","execution_id":"execution-9",'
        b'"sequence":1,"stream":"stdout","data":"h\xc3\xa9llo"}\n'
    )

    assert PROTOCOL == "sandbox-executor-v1"
    assert encode_request(request) == request_wire
    assert decode_request(request_wire) == request
    assert encode_response(response) == response_wire
    assert decode_response(response_wire) == response


@pytest.mark.parametrize(
    "request_frame",
    [
        {
            "protocol": PROTOCOL,
            "type": "ensure_workspace",
            "request_id": "request-1",
            "execution_id": "execution-1",
            "tool_call_id": "tool-1",
            "workspace_id": "workspace-1",
        },
        {
            "protocol": PROTOCOL,
            "type": "attach_execution",
            "request_id": "request-2",
            "execution_id": "execution-1",
            "tool_call_id": "tool-2",
            "offset": 4096,
        },
        {
            "protocol": PROTOCOL,
            "type": "cancel_execution",
            "request_id": "request-3",
            "execution_id": "execution-1",
            "tool_call_id": "tool-3",
        },
        {
            "protocol": PROTOCOL,
            "type": "read_file",
            "request_id": "request-4",
            "execution_id": "execution-1",
            "tool_call_id": "tool-4",
            "path": "../literal/./path.txt",
            "offset": 5,
            "max_bytes": 8192,
        },
        {
            "protocol": PROTOCOL,
            "type": "health",
            "request_id": "request-5",
            "execution_id": "execution-health",
        },
    ],
)
def test_each_request_type_round_trips_without_resolving_content(
    request_frame: dict[str, object],
) -> None:
    assert decode_request(encode_request(request_frame)) == request_frame


@pytest.mark.parametrize(
    "response_frame",
    [
        {
            "protocol": PROTOCOL,
            "type": "acknowledged",
            "request_id": "request-1",
            "execution_id": "execution-1",
            "operation": "exec",
        },
        {
            "protocol": PROTOCOL,
            "type": "read_result",
            "request_id": "request-2",
            "execution_id": "execution-1",
            "path": "../literal/path.txt",
            "offset": 2,
            "data": "llo",
            "eof": True,
        },
        {
            "protocol": PROTOCOL,
            "type": "health_result",
            "request_id": "request-3",
            "execution_id": "execution-health",
            "status": "ok",
        },
        {
            "protocol": PROTOCOL,
            "type": "terminal",
            "request_id": "request-4",
            "execution_id": "execution-1",
            "status": "completed",
            "exit_code": 0,
            "error": None,
        },
    ],
)
def test_each_response_type_round_trips(response_frame: dict[str, object]) -> None:
    assert decode_response(encode_response(response_frame)) == response_frame


def test_rejects_malformed_oversized_and_non_utf8_frames() -> None:
    invalid_frames = [
        b"not-json\n",
        b'{"protocol":"sandbox-executor-v1"}\ntrailing\n',
        b"\xff\n",
        b"{" + b" " * MAX_FRAME_BYTES,
    ]

    for frame in invalid_frames:
        with pytest.raises(ProtocolError):
            decode_request(frame)

    invalid_text = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-1",
        "execution_id": "execution-1",
        "tool_call_id": "tool-1",
        "workspace_id": "workspace-1",
        "command": "\ud800",
        "timeout_ms": 1000,
    }
    with pytest.raises(ProtocolError):
        encode_request(invalid_text)


def test_rejects_missing_extra_and_bad_identity_fields() -> None:
    valid = {
        "protocol": PROTOCOL,
        "type": "cancel_execution",
        "request_id": "request-1",
        "execution_id": "execution-1",
        "tool_call_id": "tool-1",
    }
    invalid = [
        {key: value for key, value in valid.items() if key != "request_id"},
        {**valid, "unexpected": True},
        {**valid, "request_id": "../request"},
        {**valid, "execution_id": ""},
        {**valid, "tool_call_id": "tool\n2"},
    ]

    for frame in invalid:
        with pytest.raises(ProtocolError):
            encode_request(frame)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("command", "x" * (MAX_COMMAND_BYTES + 1)),
        ("timeout_ms", MAX_TIMEOUT_MS + 1),
    ],
)
def test_rejects_oversized_exec_inputs(field: str, value: object) -> None:
    frame = {
        "protocol": PROTOCOL,
        "type": "exec",
        "request_id": "request-1",
        "execution_id": "execution-1",
        "tool_call_id": "tool-1",
        "workspace_id": "workspace-1",
        "command": "pwd",
        "timeout_ms": 1000,
    }
    frame[field] = value

    with pytest.raises(ProtocolError):
        encode_request(frame)


@pytest.mark.parametrize(
    ("request_type", "field", "value"),
    [
        ("read_file", "tool_call_id", "t" * (MAX_TOOL_CALL_ID_BYTES + 1)),
        ("read_file", "path", "p" * (MAX_PATH_BYTES + 1)),
        ("read_file", "offset", MAX_OFFSET + 1),
        ("read_file", "max_bytes", MAX_READ_BYTES + 1),
        ("attach_execution", "offset", MAX_OFFSET + 1),
    ],
)
def test_rejects_bounded_read_and_attach_values(
    request_type: str, field: str, value: object
) -> None:
    request_frame = {
        "protocol": PROTOCOL,
        "type": request_type,
        "request_id": "request-1",
        "execution_id": "execution-1",
        "tool_call_id": "tool-1",
        "path": "path.txt",
        "offset": 0,
        "max_bytes": 4096,
    }
    if request_type == "attach_execution":
        del request_frame["path"]
        del request_frame["max_bytes"]
    request_frame[field] = value

    with pytest.raises(ProtocolError):
        encode_request(request_frame)


def test_rejects_oversized_output_chunk() -> None:
    output = {
        "protocol": PROTOCOL,
        "type": "output",
        "request_id": "request-1",
        "execution_id": "execution-1",
        "sequence": 0,
        "stream": "stdout",
        "data": "x" * (MAX_OUTPUT_CHUNK_BYTES + 1),
    }

    with pytest.raises(ProtocolError):
        encode_response(output)


def _execution_response(kind: str, **fields: object) -> dict[str, object]:
    return {
        "protocol": PROTOCOL,
        "type": kind,
        "request_id": "request-1",
        "execution_id": "execution-1",
        **fields,
    }


def test_validates_increasing_output_and_exactly_one_terminal_response() -> None:
    responses = [
        _execution_response("acknowledged", operation="exec"),
        _execution_response("output", sequence=4, stream="stdout", data="one"),
        _execution_response("output", sequence=9, stream="stderr", data="two"),
        _execution_response("terminal", status="completed", exit_code=0, error=None),
    ]

    validate_response_sequence(
        responses, request_id="request-1", execution_id="execution-1"
    )

    validator = ResponseSequenceValidator("request-1", "execution-1")
    for response in responses:
        validator.accept(response)
    validator.finish()


@pytest.mark.parametrize(
    "responses",
    [
        [
            _execution_response("output", sequence=2, stream="stdout", data="a"),
            _execution_response("output", sequence=2, stream="stdout", data="b"),
            _execution_response(
                "terminal", status="completed", exit_code=0, error=None
            ),
        ],
        [
            _execution_response(
                "terminal", status="completed", exit_code=0, error=None
            ),
            _execution_response("output", sequence=3, stream="stdout", data="late"),
        ],
        [_execution_response("output", sequence=1, stream="stdout", data="open")],
        [
            _execution_response(
                "terminal", status="completed", exit_code=0, error=None
            ),
            _execution_response(
                "terminal", status="completed", exit_code=0, error=None
            ),
        ],
        [
            {
                **_execution_response(
                    "terminal", status="completed", exit_code=0, error=None
                ),
                "execution_id": "execution-other",
            }
        ],
    ],
)
def test_rejects_invalid_output_and_terminal_ordering(
    responses: list[dict[str, object]],
) -> None:
    with pytest.raises(ProtocolError):
        validate_response_sequence(
            responses, request_id="request-1", execution_id="execution-1"
        )
