"""End-to-end contract for synchronizing the chat task taxonomy snapshot."""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from backend.chat_sandbox_worker.update_worker_contract import (
    bump_version,
    set_image_id,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_sync_command_updates_catalog_and_detects_stale_output(tmp_path: Path):
    tasks = [
        {
            "name": f"Task {index:02d}",
            "slug": f"task-{index:02d}",
            "level": 0,
            "paper_count": index,
        }
        for index in range(49)
    ]
    tasks.append(
        {
            "name": "Text Reranking",
            "slug": "text-reranking",
            "level": 2,
            "paper_count": 630,
        }
    )
    areas = {
        "results": [
            {
                "name": "General",
                "tasks": [tasks[0]],
            }
        ]
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/v1/areas/with-tasks/":
                payload = areas
            elif self.path.startswith("/api/v1/tasks/"):
                payload = {
                    "count": len(tasks),
                    "next_page": None,
                    "previous_page": None,
                    "results": tasks,
                }
            else:
                self.send_error(404)
                return
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    output = tmp_path / "TASK_CATALOG.md"
    command = [
        sys.executable,
        "-m",
        "backend.chat_sandbox_worker.sync_task_catalog",
        "--api-url",
        f"http://127.0.0.1:{server.server_port}/api/v1",
        "--output",
        str(output),
    ]
    try:
        updated = subprocess.run(command, check=False, capture_output=True, text=True)
        assert updated.returncode == 0, updated.stderr
        assert "`text-reranking` — Text Reranking" in output.read_text()

        output.write_text("stale\n")
        stale = subprocess.run(
            [*command, "--check"], check=False, capture_output=True, text=True
        )
        assert stale.returncode == 1
        assert "is stale" in stale.stderr

        subprocess.run(command, check=True)
        current = subprocess.run(
            [*command, "--check"], check=False, capture_output=True, text=True
        )
        assert current.returncode == 0
    finally:
        server.shutdown()
        thread.join()


def test_worker_contract_update_is_bounded_to_staging_fields(tmp_path: Path):
    contract = tmp_path / "contract.py"
    contract.write_text(
        'WORKER_CONTRACT_VERSION = "96"\n'
        'MODAL_IMAGE_ID = "im-old"\n'
        'PRODUCTION_MODAL_IMAGE_ID = "im-production"\n'
    )

    assert bump_version(contract) == "97"
    set_image_id("im-new123", contract)

    updated = contract.read_text()
    assert 'WORKER_CONTRACT_VERSION = "97"' in updated
    assert 'MODAL_IMAGE_ID = "im-new123"' in updated
    assert 'PRODUCTION_MODAL_IMAGE_ID = "im-production"' in updated


def test_task_catalog_sync_workflow_is_scheduled_and_deploys_staging():
    workflow = (
        REPOSITORY_ROOT / ".github/workflows/sync-chat-task-catalog.yml"
    ).read_text()

    assert 'cron: "*/15 * * * *"' in workflow
    assert "workflow_dispatch:" in workflow
    assert "permissions:\n  contents: write" in workflow
    assert "uv run --no-project --python 3.12 --env-file backend/keys.env" in workflow
    assert "python -m backend.chat_sandbox_worker.sync_task_catalog" in workflow
    assert "python backend/chat_sandbox_worker/publish_image.py" in workflow
    assert 'git add "$DESTINATION" "$CONTRACT"' in workflow
    assert "sudo /usr/local/sbin/pwc-deploy staging '$RELEASE_SHA'" in workflow
