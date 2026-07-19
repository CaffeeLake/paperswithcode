# /// script
# requires-python = ">=3.12"
# ///
"""Serve, export, merge, adjudicate, and validate blinded related-paper labels."""

from __future__ import annotations

import argparse
import json
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from backend.services.embedding_annotation import (
    SCHEMA_VERSION,
    assignment_sha256,
    atomic_write_json,
    build_assignment,
    export_annotations,
    merge_exports,
    now_iso,
    read_jsonl,
    validate_adjudicated,
    validate_label,
    verify_checksum_manifest,
)


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Papers With Code relevance annotation</title>
<style>
:root{font-family:system-ui,sans-serif;color:#17202a;background:#f4f6f8}body{margin:0}main{max-width:980px;margin:auto;padding:24px}
.bar,.card{background:white;border:1px solid #dce2e7;border-radius:12px;padding:18px;margin-bottom:16px}.bar{position:sticky;top:0;z-index:2}
h1{font-size:20px;margin:0 0 8px}h2{font-size:18px;margin:0 0 8px}.abstract{white-space:pre-wrap;line-height:1.45;color:#34495e}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}.actions{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}
button{border:1px solid #9aa8b4;background:white;border-radius:8px;padding:10px 14px;cursor:pointer}button.primary{background:#1f6feb;color:white;border-color:#1f6feb}
textarea{width:100%;min-height:70px;box-sizing:border-box}progress{width:100%}.muted{color:#637381;font-size:13px}.hidden{display:none}
@media(max-width:720px){.pair{grid-template-columns:1fr}}
</style></head><body><main>
<div class="bar"><h1>Blinded related-paper judgments</h1><div id="identity" class="muted"></div><progress id="progress"></progress><div id="count" class="muted"></div></div>
<section id="annotation" class="hidden"><div class="pair"><article class="card"><h2 id="sourceTitle"></h2><div id="sourceAbstract" class="abstract"></div></article><article class="card"><h2 id="candidateTitle"></h2><div id="candidateAbstract" class="abstract"></div></article></div>
<div class="card"><strong>Would the candidate be a useful next paper for someone researching the source paper's central technical contribution?</strong>
<div class="actions"><button onclick="save('graded',2)" class="primary">2 — strongly related</button><button onclick="save('graded',1)">1 — somewhat related</button><button onclick="save('graded',0)">0 — unrelated</button><button onclick="save('unsure',null)">Unsure</button><button onclick="save('skipped',null)">Skip</button></div>
<label>Optional note<textarea id="notes"></textarea></label><div class="actions"><button onclick="previous()">Previous</button></div></div></section>
<section id="adjudication" class="hidden"><div class="card"><h2>Adjudicate disagreement</h2><pre id="prior"></pre><div class="actions"><button onclick="adjudicate(2)" class="primary">Final 2</button><button onclick="adjudicate(1)">Final 1</button><button onclick="adjudicate(0)">Final 0</button></div><label>Adjudication note<textarea id="adjNotes"></textarea></label></div></section>
<div id="done" class="card hidden"><h2>Assignment complete</h2><p>Progress is saved. Use the export command from the dataset card to create a validated JSONL export.</p><button onclick="previous()">Review previous</button></div>
</main><script>
let data,position=0; async function init(){data=await (await fetch('/api/bootstrap')).json();document.getElementById('identity').textContent=data.identity;show();}
function current(){return data.items[position]}
function show(){const total=data.items.length,labels=data.labels||{};while(position<total&&labels[current().item_id])position++;document.getElementById('progress').max=total;document.getElementById('progress').value=Object.keys(labels).length;document.getElementById('count').textContent=`${Object.keys(labels).length} / ${total}`;document.getElementById('annotation').classList.toggle('hidden',data.mode!=='annotate'||position>=total);document.getElementById('adjudication').classList.toggle('hidden',data.mode!=='adjudicate'||position>=total);document.getElementById('done').classList.toggle('hidden',position<total);if(position>=total)return;const x=current();if(data.mode==='annotate'){sourceTitle.textContent=x.source_title;sourceAbstract.textContent=x.source_abstract;candidateTitle.textContent=x.candidate_title;candidateAbstract.textContent=x.candidate_abstract;notes.value=(labels[x.item_id]||{}).notes||'';}else{prior.textContent=JSON.stringify(x.annotations,null,2);adjNotes.value=x.adjudication_notes||'';}}
async function save(status,grade){const x=current();await fetch('/api/label',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({item_id:x.item_id,status,grade,notes:notes.value})});data.labels[x.item_id]={status,grade,notes:notes.value};position++;show()}
async function adjudicate(grade){const x=current();await fetch('/api/label',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({item_id:x.item_id,grade,notes:adjNotes.value})});data.labels[x.item_id]={grade,notes:adjNotes.value};position++;show()}
function previous(){position=Math.max(0,position-1);show()} init();
</script></body></html>"""


class AnnotationHandler(BaseHTTPRequestHandler):
    server: "AnnotationServer"

    def log_message(self, format: str, *args: object) -> None:
        return

    def respond_json(self, value: object, status: int = 200) -> None:
        body = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            body = HTML.encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/bootstrap":
            self.respond_json(self.server.bootstrap())
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if urlparse(self.path).path != "/api/label":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            self.server.save(payload)
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            self.respond_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        self.respond_json({"saved": True})


class AnnotationServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        mode: str,
        items: list[dict],
        state_path: Path,
        identity: str,
    ):
        super().__init__(address, AnnotationHandler)
        self.mode = mode
        self.items = items
        self.state_path = state_path
        self.identity = identity
        self.item_ids = {row["item_id"] for row in items}
        assignment_digest = assignment_sha256(items)
        if state_path.exists():
            self.state = json.loads(state_path.read_text(encoding="utf-8"))
            if self.state.get("assignment_sha256") != assignment_digest:
                raise ValueError("Saved state belongs to a different assignment")
        else:
            self.state = {
                "schema_version": SCHEMA_VERSION,
                "annotator_id": identity,
                "assignment_sha256": assignment_digest,
                "labels": {},
            }
            atomic_write_json(state_path, self.state)

    def bootstrap(self) -> dict:
        return {
            "mode": self.mode,
            "identity": self.identity,
            "items": self.items,
            "labels": self.state["labels"],
        }

    def save(self, payload: dict) -> None:
        item_id = payload["item_id"]
        if item_id not in self.item_ids:
            raise ValueError("Unknown assignment item")
        if self.mode == "annotate":
            label = {
                "status": payload["status"],
                "grade": payload.get("grade"),
                "notes": payload.get("notes") or None,
                "updated_at": now_iso(),
            }
            validate_label(label)
        else:
            if payload.get("grade") not in {0, 1, 2}:
                raise ValueError("Adjudication requires grade 0, 1, or 2")
            label = {
                "grade": payload["grade"],
                "notes": payload.get("notes") or None,
                "updated_at": now_iso(),
            }
        self.state["labels"][item_id] = label
        atomic_write_json(self.state_path, self.state)


def assignment_from_args(args: argparse.Namespace) -> list[dict]:
    return build_assignment(
        read_jsonl(args.tranche),
        args.annotator_id,
        args.annotator_index,
        args.annotator_count,
        overlap=args.overlap,
        duplicate_rate=args.duplicate_rate,
        trap_rate=args.trap_rate,
        seed=args.seed,
    )


def state_path(args: argparse.Namespace) -> Path:
    return args.state_dir / f"{args.annotator_id}.json"


def serve(args: argparse.Namespace) -> None:
    assignment = assignment_from_args(args)
    server = AnnotationServer(
        (args.host, args.port),
        "annotate",
        assignment,
        state_path(args),
        args.annotator_id,
    )
    url = f"http://{args.host}:{server.server_port}/"
    print(
        json.dumps(
            {"url": url, "assigned": len(assignment), "state": str(state_path(args))},
            indent=2,
        )
    )
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAnnotation server stopped; saved progress is intact.")
    finally:
        server.server_close()


def serve_adjudication(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.merged)
    items = []
    for row in rows:
        if row["needs_adjudication"]:
            item = dict(row)
            item["item_id"] = row["blind_id"]
            items.append(item)
    server = AnnotationServer(
        (args.host, args.port), "adjudicate", items, args.state, "adjudicator"
    )
    url = f"http://{args.host}:{server.server_port}/"
    print(
        json.dumps(
            {"url": url, "disagreements": len(items), "state": str(args.state)},
            indent=2,
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAdjudication server stopped; saved progress is intact.")
    finally:
        server.server_close()


def export_adjudication(args: argparse.Namespace) -> None:
    rows = read_jsonl(args.merged)
    state = json.loads(args.state.read_text(encoding="utf-8"))
    labels = state.get("labels", {})
    for row in rows:
        if row["blind_id"] in labels:
            row["final_grade"] = labels[row["blind_id"]]["grade"]
            row["adjudication_notes"] = labels[row["blind_id"]].get("notes")
    from backend.services.embedding_annotation import write_jsonl

    write_jsonl(args.output, rows)
    print(json.dumps(validate_adjudicated(args.output), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_assignment_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--tranche", type=Path, required=True)
        command.add_argument("--state-dir", type=Path, required=True)
        command.add_argument("--annotator-id", required=True)
        command.add_argument("--annotator-index", type=int, required=True)
        command.add_argument("--annotator-count", type=int, required=True)
        command.add_argument("--overlap", type=float, default=0.20)
        command.add_argument("--duplicate-rate", type=float, default=0.05)
        command.add_argument("--trap-rate", type=float, default=0.02)
        command.add_argument("--seed", type=int, default=20260718)

    serve_parser = sub.add_parser("serve")
    add_assignment_options(serve_parser)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--open-browser", action="store_true")
    serve_parser.set_defaults(handler=serve)

    export_parser = sub.add_parser("export")
    add_assignment_options(export_parser)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.set_defaults(
        handler=lambda args: print(
            json.dumps(
                export_annotations(
                    assignment_from_args(args),
                    json.loads(state_path(args).read_text(encoding="utf-8")),
                    args.output,
                ),
                indent=2,
            )
        )
    )

    merge_parser = sub.add_parser("merge")
    merge_parser.add_argument("exports", nargs="+", type=Path)
    merge_parser.add_argument("--output", type=Path, required=True)
    merge_parser.set_defaults(
        handler=lambda args: print(
            json.dumps(merge_exports(args.exports, args.output), indent=2)
        )
    )

    adj_parser = sub.add_parser("serve-adjudication")
    adj_parser.add_argument("--merged", type=Path, required=True)
    adj_parser.add_argument("--state", type=Path, required=True)
    adj_parser.add_argument("--host", default="127.0.0.1")
    adj_parser.add_argument("--port", type=int, default=8766)
    adj_parser.set_defaults(handler=serve_adjudication)

    adj_export = sub.add_parser("export-adjudication")
    adj_export.add_argument("--merged", type=Path, required=True)
    adj_export.add_argument("--state", type=Path, required=True)
    adj_export.add_argument("--output", type=Path, required=True)
    adj_export.set_defaults(handler=export_adjudication)

    validate = sub.add_parser("validate")
    validate.add_argument("--adjudicated", type=Path, required=True)
    validate.set_defaults(
        handler=lambda args: print(
            json.dumps(validate_adjudicated(args.adjudicated), indent=2)
        )
    )
    verify = sub.add_parser("verify-package")
    verify.add_argument("--root", type=Path, required=True)
    verify.set_defaults(
        handler=lambda args: print(
            json.dumps(verify_checksum_manifest(args.root), indent=2)
        )
    )
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
