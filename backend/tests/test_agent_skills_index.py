import hashlib
import json
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = REPOSITORY_ROOT / "frontend/public/.well-known/agent-skills/index.json"
SKILL_PATH = REPOSITORY_ROOT / "backend/chat_sandbox_worker/PWC_CLI_SKILL.md"


def test_agent_skills_index_matches_published_skill():
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    skill = index["skills"][0]

    assert index["$schema"] == (
        "https://schemas.agentskills.io/discovery/0.2.0/schema.json"
    )
    assert skill["name"] == "pwc-cli"
    assert skill["type"] == "skill-md"
    assert skill["url"] == (
        "https://raw.githubusercontent.com/huggingface/pwc-cli/"
        "main/standalone_cli/SKILL.md"
    )
    assert skill["description"] in SKILL_PATH.read_text(encoding="utf-8")
    digest = hashlib.sha256(SKILL_PATH.read_bytes()).hexdigest()
    assert skill["digest"] == f"sha256:{digest}"
