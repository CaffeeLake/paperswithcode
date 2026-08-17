from datetime import UTC, datetime, timedelta
import uuid

from backend.config import get_settings
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_session_service import TurnAdmission
from backend.services.chat_turn_runner import ModalChatTurnRunner


def test_modal_runner_preserves_admitted_reasoning_effort():
    captured = {}
    sentinel = object()

    class Manager:
        def run_turn(self, **kwargs):
            captured.update(kwargs)
            return sentinel

    runner = ModalChatTurnRunner(
        settings=get_settings(),
        admission=TurnAdmission(
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            user_message_id=uuid.uuid4(),
            selected_model="deepseek-ai/DeepSeek-V4-Flash-0731",
            model_route="deepseek/deepseek-v4-flash-0731",
            sdk_session_id=None,
            sdk_project_key=None,
            agent_harness="pi",
            execution_backend="modal_cli",
            reasoning_effort="low",
        ),
        prompt="content-free test prompt",
        request_id=str(uuid.uuid4()),
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        manager=Manager(),
    )

    assert runner.events() is sentinel
    assert captured["agent_harness"] == "pi"
    assert captured["model"] == "deepseek/deepseek-v4-flash-0731"
    assert captured["reasoning_effort"] == "low"
