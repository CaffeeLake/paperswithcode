"""Synchronize the living Open ASR Leaderboard into evaluation rows."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable

from gradio_client import Client
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Evaluation,
    Metric,
    Paper,
    Task,
    TaskDatasetMetric,
)
from backend.services.evaluation_service import EvaluationService

SPACE_APP_URL = "https://hf-audio-open-asr-leaderboard.hf.space"
SPACE_SOURCE_URL = "https://huggingface.co/spaces/hf-audio/open_asr_leaderboard"
LEGACY_SOURCE_URL = "https://paperswithcode.co/benchmark/open-asr-leaderboard"
DATASET_SLUG = "open-asr-leaderboard"
TASK_SLUG = "automatic-speech-recognition"
WER_METRIC = "WER"
RTFX_METRIC = "RTFx"
MANAGED_METHODOLOGY_PREFIX = "Managed by the Papers with Code Open ASR live sync."
MIN_EXPECTED_ENTRIES = 40
MAX_EXPECTED_ENTRIES = 150

DEFAULT_COLUMNS = [
    "RTFx ⬆️️",
    "License",
    "AMI-Cleaned",
    "Earnings22",
    "Gigaspeech-Cleaned",
    "LS Clean",
    "LS Other",
    "SPGISpeech",
    "Voxpopuli-AA-Cleaned",
    "Private (scripted)",
    "Private (conversational)",
]

# Exact, reviewed model-to-paper overrides. Models without a defensible paper
# remain unmatched; legacy importer rows provide additional continuity during
# the first live synchronization.
MODEL_PAPER_ARXIV_IDS: dict[str, str] = {
    "distil-whisper/distil-large-v3.5": "2311.00430",
    "efficient-speech/lite-whisper-large-v3-acc": "2502.20583",
    "espnet/owsm_ctc_v3.1_1B": "2401.16658",
    "espnet/owsm_ctc_v3.2_ft_1B": "2401.16658",
    "espnet/owsm_ctc_v4_1B": "2506.00338",
    "facebook/hubert-large-ls960-ft": "2106.07447",
    "facebook/mms-1b-all": "2305.13516",
    "facebook/wav2vec2-large-960h-lv60-self": "2006.11477",
    "ibm-granite/granite-4.0-1b-speech": "2505.08699",
    "ibm-granite/granite-speech-3.3-2b": "2505.08699",
    "ibm-granite/granite-speech-3.3-8b": "2505.08699",
    "ibm-granite/granite-speech-4.1-2b": "2505.08699",
    "ibm-granite/granite-speech-4.1-2b-nar": "2505.08699",
    "kyutai/stt-2.6b-en": "2410.00037",
    "microsoft/Phi-4-multimodal-instruct": "2503.01743",
    "microsoft/VibeVoice-ASR-HF": "2601.18184",
    "mistralai/Voxtral-Mini-3B-2507": "2507.13264",
    "mistralai/Voxtral-Mini-4B-Realtime-2602": "2602.11298",
    "mistralai/Voxtral-Small-24B-2507": "2507.13264",
    "nvidia/canary-180m-flash": "2503.05931",
    "nvidia/canary-1b-flash": "2503.05931",
    "nvidia/canary-1b-v2": "2509.14128",
    "nvidia/canary-qwen-2.5b": "2503.05931",
    "nvidia/nemotron-3.5-asr-streaming-0.6b": "2312.17279",
    "nvidia/nemotron-speech-streaming-en-0.6b": "2312.17279",
    "nvidia/parakeet-ctc-0.6b": "2305.05084",
    "nvidia/parakeet-ctc-1.1b": "2305.05084",
    "nvidia/parakeet-rnnt-0.6b": "2305.05084",
    "nvidia/parakeet-rnnt-1.1b": "2305.05084",
    "nvidia/parakeet-tdt-0.6b-v2": "2304.06795",
    "nvidia/parakeet-tdt-0.6b-v3": "2509.14128",
    "nvidia/parakeet-tdt-1.1b": "2304.06795",
    "nvidia/parakeet-tdt_ctc-110m": "2304.06795",
    "nyrahealth/CrisperWhisper": "2408.16589",
    "OpenMOSS-Team/MOSS-Transcribe-Diarize": "2601.01554",
    "openai/whisper-large-v3": "2212.04356",
    "openai/whisper-large-v3-turbo": "2212.04356",
    "Qwen/Qwen3-ASR-0.6B": "2601.21337",
    "Qwen/Qwen3-ASR-0.6B-hf": "2601.21337",
    "Qwen/Qwen3-ASR-1.7B": "2601.21337",
    "Qwen/Qwen3-ASR-1.7B-hf": "2601.21337",
    "soundsgoodai/Zipformer-cr-ctc-transducer-XL-290M": "2410.05101",
    "soundsgoodai/Zipformer-transducer-XL-290M": "2310.11230",
    "speechbrain/asr-conformer-largescaleasr": "2106.04624",
    "usefulsensors/moonshine-streaming-medium": "2602.12241",
    "usefulsensors/moonshine-streaming-small": "2602.12241",
    "usefulsensors/moonshine-streaming-tiny": "2602.12241",
    "usefulsensors/moonshine-tiny": "2410.15608",
}

_TAG_RE = re.compile(r"<[^>]+>")
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?")
_LEGACY_MODEL_RE = re.compile(r"sourced from ([^/]+/[^/]+)/\.eval_results")


@dataclass(frozen=True)
class OpenAsrEntry:
    model_id: str
    rank: int
    wer: float
    rtfx: float | None
    is_open: bool


@dataclass
class OpenAsrSyncStats:
    fetched: int = 0
    matched: int = 0
    created: int = 0
    updated: int = 0
    deleted: int = 0
    unmatched_models: list[str] = field(default_factory=list)
    missing_papers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fetched": self.fetched,
            "matched": self.matched,
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
            "unmatched_models": self.unmatched_models,
            "missing_papers": self.missing_papers,
        }


def _number(value: Any, *, optional: bool = False) -> float | None:
    if value is None or str(value).strip().upper() == "NA":
        if optional:
            return None
        raise ValueError("required numeric leaderboard value is missing")
    match = _NUMBER_RE.match(str(value).strip())
    if match is None:
        raise ValueError(f"invalid numeric leaderboard value: {value!r}")
    return float(match.group())


def parse_open_asr_leaderboard(payload: Any) -> list[OpenAsrEntry]:
    """Validate the public Space table before it can affect persisted rows."""
    if not isinstance(payload, dict):
        raise TypeError("Open ASR response must be a dataframe object")
    headers = payload.get("headers")
    rows = payload.get("data")
    if not isinstance(headers, list) or not isinstance(rows, list):
        raise TypeError("Open ASR response must contain headers and data lists")
    required = {"Rank", "model", "Average WER ⬇️", "RTFx ⬆️️", "License"}
    if not required.issubset(headers):
        raise ValueError("Open ASR response is missing required columns")
    if not MIN_EXPECTED_ENTRIES <= len(rows) <= MAX_EXPECTED_ENTRIES:
        raise ValueError(
            f"Open ASR returned {len(rows)} rows; expected "
            f"{MIN_EXPECTED_ENTRIES}-{MAX_EXPECTED_ENTRIES}"
        )

    indexes = {name: headers.index(name) for name in required}
    entries: list[OpenAsrEntry] = []
    names: set[str] = set()
    ranks: set[int] = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != len(headers):
            raise ValueError("Open ASR response contains a malformed row")
        model_id = html.unescape(_TAG_RE.sub("", str(row[indexes["model"]]))).strip()
        rank_value = _number(row[indexes["Rank"]])
        wer = _number(row[indexes["Average WER ⬇️"]])
        rtfx = _number(row[indexes["RTFx ⬆️️"]], optional=True)
        license_name = str(row[indexes["License"]]).strip()
        rank = int(rank_value) if rank_value is not None else 0
        if not model_id or len(model_id) > 255 or "/" not in model_id:
            raise ValueError("Open ASR row has an invalid model identifier")
        if rank in ranks or model_id.casefold() in names:
            raise ValueError("Open ASR response contains duplicate models or ranks")
        if (
            rank < 1
            or wer is None
            or not 0 < wer < 100
            or (rtfx is not None and rtfx <= 0)
        ):
            raise ValueError(f"Open ASR row is outside accepted bounds for {model_id}")
        ranks.add(rank)
        names.add(model_id.casefold())
        entries.append(
            OpenAsrEntry(
                model_id=model_id,
                rank=rank,
                wer=wer,
                rtfx=rtfx,
                is_open=license_name.casefold() != "proprietary",
            )
        )
    if ranks != set(range(1, len(entries) + 1)):
        raise ValueError("Open ASR ranks must be contiguous and start at one")
    return sorted(entries, key=lambda entry: entry.rank)


def fetch_open_asr_leaderboard(
    client_factory: Callable[..., Any] = Client,
) -> list[OpenAsrEntry]:
    """Fetch the Space's exact default English leaderboard table."""
    client = client_factory(SPACE_APP_URL, verbose=False)
    payload = client.predict(
        "",
        True,
        False,
        DEFAULT_COLUMNS,
        api_name="/filter_main_table",
    )
    return parse_open_asr_leaderboard(payload)


class OpenAsrSyncService:
    """Replace only live and legacy-imported Open ASR evaluation rows."""

    def __init__(self, db: Session):
        self.db = db

    def _leaderboard_identity(self) -> tuple[Task, Dataset]:
        task = self.db.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
        dataset = (
            self.db.query(Dataset).filter(Dataset.slug == DATASET_SLUG).one_or_none()
        )
        metrics = {
            metric.name: metric
            for metric in self.db.query(Metric)
            .filter(Metric.name.in_((WER_METRIC, RTFX_METRIC)))
            .all()
        }
        if task is None or dataset is None or set(metrics) != {WER_METRIC, RTFX_METRIC}:
            raise RuntimeError(
                "Open ASR task, benchmark, or metrics are not configured"
            )
        configured = {
            row.metric_id
            for row in self.db.query(TaskDatasetMetric)
            .filter(
                TaskDatasetMetric.task_id == task.id,
                TaskDatasetMetric.dataset_id == dataset.id,
            )
            .all()
        }
        if {metric.id for metric in metrics.values()} - configured:
            raise RuntimeError(
                "Open ASR leaderboard metrics are not linked to the task"
            )
        return task, dataset

    @staticmethod
    def _legacy_model_id(row: Evaluation) -> str | None:
        match = _LEGACY_MODEL_RE.search(row.methodology or "")
        return match.group(1) if match else None

    def sync(
        self,
        entries: list[OpenAsrEntry],
        *,
        fetched_at: datetime | None = None,
        commit: bool = True,
    ) -> OpenAsrSyncStats:
        if not entries:
            raise ValueError("Refusing to synchronize an empty Open ASR leaderboard")
        now = fetched_at or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        stats = OpenAsrSyncStats(fetched=len(entries))

        try:
            task, dataset = self._leaderboard_identity()
            papers_by_arxiv = {
                paper.arxiv_id: paper.id
                for paper in self.db.query(Paper)
                .filter(
                    Paper.arxiv_id.in_(set(MODEL_PAPER_ARXIV_IDS.values())),
                    Paper.is_latest_version,
                )
                .all()
            }
            candidate_rows = (
                self.db.query(Evaluation)
                .filter(
                    Evaluation.task_id == task.id,
                    Evaluation.dataset_id == dataset.id,
                )
                .all()
            )
            managed_rows = [
                row
                for row in candidate_rows
                if row.external_source_url == SPACE_SOURCE_URL
                and (row.methodology or "").startswith(MANAGED_METHODOLOGY_PREFIX)
            ]
            legacy_rows = [
                row
                for row in candidate_rows
                if row.external_source_url == LEGACY_SOURCE_URL
                and (row.methodology or "").startswith("Open ASR Leaderboard rank ")
                and self._legacy_model_id(row) is not None
            ]
            managed_by_name = {row.model_name.casefold(): row for row in managed_rows}
            legacy_papers = {
                self._legacy_model_id(row).casefold(): row.paper_id
                for row in legacy_rows
            }
            upstream_names = {entry.model_id.casefold() for entry in entries}

            for entry in entries:
                key = entry.model_id.casefold()
                row = managed_by_name.get(key)
                paper_id = row.paper_id if row is not None else legacy_papers.get(key)
                if paper_id is None:
                    arxiv_id = MODEL_PAPER_ARXIV_IDS.get(entry.model_id)
                    if arxiv_id is None:
                        stats.unmatched_models.append(entry.model_id)
                        continue
                    paper_id = papers_by_arxiv.get(arxiv_id)
                    if paper_id is None:
                        stats.missing_papers.append(f"{entry.model_id}:{arxiv_id}")
                        continue

                methodology = (
                    f"{MANAGED_METHODOLOGY_PREFIX} Upstream rank {entry.rank}; "
                    f"default Average WER; fetched {now.isoformat()}."
                )
                if row is None:
                    row = Evaluation(
                        paper_id=paper_id,
                        task_id=task.id,
                        dataset_id=dataset.id,
                        model_name=entry.model_id,
                    )
                    self.db.add(row)
                    stats.created += 1
                else:
                    stats.updated += 1
                metrics: dict[str, float] = {WER_METRIC: entry.wer}
                if entry.rtfx is not None:
                    metrics[RTFX_METRIC] = entry.rtfx
                row.paper_id = paper_id
                row.methodology = methodology
                row.metrics = metrics
                row.uses_additional_data = False
                row.is_open = entry.is_open
                row.best_metric = WER_METRIC
                row.evaluated_on = now.date()
                row.external_source_url = SPACE_SOURCE_URL
                row.source_url = SPACE_SOURCE_URL
                row.external = True
                row.updated_at = now
                stats.matched += 1

            for row in managed_rows:
                if row.model_name.casefold() not in upstream_names:
                    self.db.delete(row)
                    stats.deleted += 1
            # These rows came from the retired one-shot importer. Once a valid
            # live table has been processed, its replacements are authoritative.
            for row in legacy_rows:
                self.db.delete(row)
                stats.deleted += 1

            self.db.flush()
            EvaluationService(self.db).recalculate_ranks(
                task.id, dataset.id, metric_name=WER_METRIC, commit=False
            )
            if commit:
                self.db.commit()
            else:
                self.db.rollback()
            return stats
        except Exception:
            self.db.rollback()
            raise
