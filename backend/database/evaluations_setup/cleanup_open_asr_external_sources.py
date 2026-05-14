"""
One-shot cleanup pass over the external `papers` rows that the Open ASR
importer left behind for Hugging Face model release pages.

The original `import_open_asr_evaluations.py` falls back to creating a
`source='external'` paper per HF model_id whenever it cannot resolve a
canonical arXiv paper. That produces near-duplicate rows for model
families (Moonshine Streaming tiny/small/medium, Niagara 19m/38m) and
also creates external rows for models whose canonical arXiv paper does
exist in the database but is not declared as an `arxiv:` tag on the
model card (espnet/owsm_ctc_v3.1_1B, espnet/owsm_ctc_v4_1B).

This script:

1. Consolidates Moonshine Streaming variants into a single external row.
2. Consolidates ABR Niagara variants into a single external row.
3. Relinks `espnet/owsm_ctc_v3.1_1B` evaluations to arXiv `2401.16658`
   and `espnet/owsm_ctc_v4_1B` evaluations to arXiv `2506.00338`,
   then drops the now-orphan external rows.
4. Adds a `repositories` row for `https://github.com/zai-org/GLM-ASR`
   and links it to the GLM-ASR-Nano-2512 external paper.
5. Backfills concise abstracts for the remaining HF-model external
   paper rows that should stay external.

It also ensures every paper that has an evaluation on the Automatic
Speech Recognition task is tagged with that task in `paper_tasks`. The
Open ASR importer deliberately rebuilds evaluations only, so without
this step a few arXiv-backed and external HF papers end up on the
leaderboard without appearing on the ASR task page.

The script is idempotent: re-running after success is a no-op.

Run with:

    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/cleanup_open_asr_external_sources.py
"""

from __future__ import annotations

import logging
import sys
from textwrap import dedent

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import (
    Evaluation as DBEvaluation,
    Paper as DBPaper,
    PaperRepository as DBPaperRepository,
    PaperTask as DBPaperTask,
    Repository as DBRepository,
    Task as DBTask,
)

ASR_TASK_SLUG = "automatic-speech-recognition"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


MOONSHINE_HF_URLS = [
    "https://huggingface.co/UsefulSensors/moonshine-streaming-tiny",
    "https://huggingface.co/UsefulSensors/moonshine-streaming-small",
    "https://huggingface.co/UsefulSensors/moonshine-streaming-medium",
]
MOONSHINE_CANONICAL_URL = (
    "https://huggingface.co/UsefulSensors/moonshine-streaming-medium"
)
MOONSHINE_TITLE = "Moonshine Streaming"
MOONSHINE_ABSTRACT = dedent(
    """
    Moonshine Streaming is a family of low-latency English automatic speech
    recognition models from Useful Sensors. The architecture pairs a lightweight
    50 Hz audio frontend with a sliding-window Transformer encoder that uses
    bounded local attention and no positional embeddings (an "ergodic" encoder),
    an adapter that injects positional information, and an autoregressive
    Transformer decoder. Three sizes are released - Tiny (34M), Small (123M),
    and Medium (245M) - trained on roughly 300K hours of speech and targeted
    at edge-class hardware (roughly 0.1-1 TOPS and sub-1 GB memory budgets)
    for use cases like live captioning, voice commands, and real-time
    transcription.
    """
).strip()

NIAGARA_HF_URLS = [
    "https://huggingface.co/abr-ai/niagara-19m-batch.en",
    "https://huggingface.co/abr-ai/niagara-38m-batch.en",
]
NIAGARA_CANONICAL_URL = "https://huggingface.co/abr-ai/niagara-38m-batch.en"
NIAGARA_TITLE = "Niagara Batch English SSM"
NIAGARA_ABSTRACT = dedent(
    """
    Niagara is Applied Brain Research's family of English automatic speech
    recognition models built as state space models (SSMs) with attention. The
    Niagara Batch English variants are non-causal SSM ASR checkpoints trained
    on about 50K hours of speech using MFCC inputs, CTC loss, greedy decoding,
    and SentencePiece tokenization, and are designed for direct comparison
    against other models on the Open ASR Leaderboard. Two sizes are released
    (19M and 38M parameters) to demonstrate that small, real-time, accurate
    ASR can run on low-cost edge hardware; ABR also ships streaming variants
    with sub-120 ms latency, punctuation, capitalization, and custom
    vocabulary under a commercial license.
    """
).strip()

OWSM_RELINKS = [
    {
        "external_url": "https://huggingface.co/espnet/owsm_ctc_v3.1_1B",
        "arxiv_id": "2401.16658",
    },
    {
        "external_url": "https://huggingface.co/espnet/owsm_ctc_v4_1B",
        "arxiv_id": "2506.00338",
    },
]

GLM_ASR_EXTERNAL_URL = "https://huggingface.co/zai-org/GLM-ASR-Nano-2512"
GLM_ASR_GITHUB_URL = "https://github.com/zai-org/GLM-ASR"
GLM_ASR_TITLE = "GLM-ASR-Nano-2512"
GLM_ASR_ABSTRACT = dedent(
    """
    GLM-ASR-Nano-2512 is a 1.5B-parameter open-source automatic speech
    recognition model from Z.ai (zai-org) targeted at real-world acoustic
    complexity. The model is optimized for Mandarin, English, Cantonese, and
    other Chinese dialects, and is specifically trained for "whisper/quiet
    speech" scenarios so it can transcribe very low-volume audio that
    traditional models often miss. The release reports the lowest average
    error rate (4.10) among comparable open-source models with significant
    advantages on Chinese benchmarks such as Wenet Meeting and Aishell-1,
    while outperforming OpenAI Whisper V3 at a much smaller parameter count.
    """
).strip()

REMAINING_ABSTRACTS: dict[str, str] = {
    "https://huggingface.co/okestro-ai-lab/SYMPHONY-ASR": dedent(
        """
        SYMPHONY-ASR is an automatic speech recognition specialized model from
        Okestro AI Lab that adapts a pre-trained large language model to the
        audio modality for speech-to-text transcription. It targets efficient
        long-form speech processing (up to roughly 8 hours of audio on a 40 GB
        GPU), bilingual Korean and English support in a single model, and
        preservation of the underlying LLM's text-only capabilities via a
        disable-LoRA mechanism. The release reports evaluations on standard
        ASR benchmarks.
        """
    ).strip(),
    "https://huggingface.co/okestro-ai-lab/SYMPHONY": dedent(
        """
        SYMPHONY is an LLM-based speech model from Okestro AI Lab focused on
        efficient long-form speech-to-text transcription. The model adapts a
        pre-trained LLM to audio with a low speech-token rate (1.67 tokens
        per second), supports bilingual Korean and English use in a single
        model, and reports evaluation results on standard ASR benchmarks.
        """
    ).strip(),
    "https://huggingface.co/nvidia/canary-1b-v2": dedent(
        """
        Canary-1B-v2 is a 1-billion-parameter multitask speech transcription
        and translation model from NVIDIA, built on a FastConformer encoder
        (32 layers) and a Transformer decoder (8 layers). It supports
        automatic speech recognition (ASR) in 25 European languages and
        bidirectional English speech translation (AST) across 24 of them,
        with automatic punctuation, capitalization, and word- and
        segment-level timestamps. The model is trained on the full Granary
        dataset, achieves performance comparable to systems three times its
        size while being up to 10x faster, and is released under a permissive
        CC BY 4.0 license. Architectural details and full evaluations are in
        the Canary-1b-v2 Technical Report (arXiv:2509.14128).
        """
    ).strip(),
    "https://huggingface.co/speechbrain/asr-conformer-loquacious": dedent(
        """
        This SpeechBrain checkpoint is a 480M-parameter Conformer encoder
        combined with a joint CTC/Transformer decoder for English automatic
        speech recognition, trained on the 25,000-hour LargeScaleASR
        ("Loquacious") dataset. It uses a unigram subword tokenizer and 16
        kHz mono input, and reports 6.8% validation WER and 7.5% test WER on
        the in-domain set, 4.6% WER on LibriSpeech test-other, 12.0% on
        Common Voice 18 test, and 6.9% on VoxPopuli test. It is intended as
        an open research and commercial baseline for transcription on
        diverse English speech.
        """
    ).strip(),
    "https://huggingface.co/nvidia/canary-1b": dedent(
        """
        NVIDIA Canary-1B is a 1-billion-parameter multilingual, multitasking
        speech model that targets state-of-the-art performance on automatic
        speech recognition (ASR) and speech translation (AST). It supports
        ASR in English, German, French, and Spanish, plus translation between
        English and each of those three languages, with optional punctuation
        and capitalization. The architecture combines a 24-layer FastConformer
        encoder with a 24-layer Transformer decoder and uses a concatenated
        SentencePiece tokenizer that makes scaling to more languages
        straightforward.
        """
    ).strip(),
}


def consolidate_family(
    db: Session,
    *,
    family_label: str,
    canonical_url: str,
    variant_urls: list[str],
    title: str,
    abstract: str,
    hf_models: list[str],
) -> None:
    """Merge a family of `source='external'` HF model rows into one row.

    The canonical row gets the family title/abstract/hf_models and absorbs
    every evaluation that previously pointed at a variant row. Each
    evaluation keeps its per-variant `external_source_url`, so the
    leaderboard still links each entry to the right HF model.
    """
    canonical = (
        db.query(DBPaper)
        .filter(
            DBPaper.source == "external",
            DBPaper.source_url == canonical_url,
        )
        .first()
    )
    if canonical is None:
        logger.warning(
            "[%s] canonical row %s missing; skipping consolidation",
            family_label,
            canonical_url,
        )
        return

    variant_ids: list[int] = []
    for variant_url in variant_urls:
        if variant_url == canonical_url:
            continue
        variant = (
            db.query(DBPaper)
            .filter(
                DBPaper.source == "external",
                DBPaper.source_url == variant_url,
            )
            .first()
        )
        if variant is None:
            logger.info("[%s] variant %s already removed", family_label, variant_url)
            continue
        moved = (
            db.query(DBEvaluation)
            .filter(DBEvaluation.paper_id == variant.id)
            .update({DBEvaluation.paper_id: canonical.id}, synchronize_session=False)
        )
        logger.info(
            "[%s] moved %d evaluations from paper id=%d (%s) to id=%d",
            family_label,
            moved,
            variant.id,
            variant_url,
            canonical.id,
        )
        variant_ids.append(variant.id)

    canonical.title = title
    canonical.abstract = abstract
    canonical.hf_models = list(hf_models)

    db.flush()

    if variant_ids:
        deleted = (
            db.query(DBPaper)
            .filter(DBPaper.id.in_(variant_ids))
            .delete(synchronize_session=False)
        )
        logger.info(
            "[%s] deleted %d redundant external paper rows", family_label, deleted
        )


def relink_owsm_to_arxiv(db: Session) -> None:
    """Move evaluations from each OWSM HF external row to its arXiv paper."""
    for entry in OWSM_RELINKS:
        external = (
            db.query(DBPaper)
            .filter(
                DBPaper.source == "external",
                DBPaper.source_url == entry["external_url"],
            )
            .first()
        )
        canonical = (
            db.query(DBPaper)
            .filter(
                DBPaper.arxiv_id == entry["arxiv_id"],
                DBPaper.is_latest_version,
            )
            .first()
        )
        if canonical is None:
            logger.warning(
                "[owsm] arxiv paper %s missing; skipping %s",
                entry["arxiv_id"],
                entry["external_url"],
            )
            continue
        if external is None:
            logger.info("[owsm] external row %s already removed", entry["external_url"])
            existing_hf = list(canonical.hf_models or [])
            if entry["external_url"] not in existing_hf:
                existing_hf.append(entry["external_url"])
                canonical.hf_models = existing_hf
            continue
        moved = (
            db.query(DBEvaluation)
            .filter(DBEvaluation.paper_id == external.id)
            .update({DBEvaluation.paper_id: canonical.id}, synchronize_session=False)
        )
        logger.info(
            "[owsm] moved %d evaluations from %s (id=%d) to arxiv:%s (id=%d)",
            moved,
            entry["external_url"],
            external.id,
            entry["arxiv_id"],
            canonical.id,
        )

        existing_hf = list(canonical.hf_models or [])
        if entry["external_url"] not in existing_hf:
            existing_hf.append(entry["external_url"])
            canonical.hf_models = existing_hf

        db.flush()
        db.delete(external)
        logger.info(
            "[owsm] deleted external paper id=%d (%s)",
            external.id,
            entry["external_url"],
        )


def link_glm_asr_repo(db: Session) -> None:
    """Attach the zai-org/GLM-ASR GitHub repository to the GLM-ASR paper row."""
    paper = (
        db.query(DBPaper)
        .filter(
            DBPaper.source == "external",
            DBPaper.source_url == GLM_ASR_EXTERNAL_URL,
        )
        .first()
    )
    if paper is None:
        logger.warning(
            "[glm-asr] external row %s missing; skipping repo link",
            GLM_ASR_EXTERNAL_URL,
        )
        return

    paper.title = GLM_ASR_TITLE
    paper.abstract = GLM_ASR_ABSTRACT

    repo = db.query(DBRepository).filter(DBRepository.url == GLM_ASR_GITHUB_URL).first()
    if repo is None:
        repo = DBRepository(
            url=GLM_ASR_GITHUB_URL,
            owner="zai-org",
            name="GLM-ASR",
            num_stars=0,
            source="manual",
        )
        db.add(repo)
        db.flush()
        logger.info("[glm-asr] created repository row id=%d", repo.id)

    existing_link = (
        db.query(DBPaperRepository)
        .filter(
            DBPaperRepository.paper_id == paper.id,
            DBPaperRepository.repository_id == repo.id,
        )
        .first()
    )
    if existing_link is None:
        db.add(
            DBPaperRepository(
                paper_id=paper.id,
                repository_id=repo.id,
                is_official=True,
            )
        )
        logger.info(
            "[glm-asr] linked paper id=%d to repository id=%d",
            paper.id,
            repo.id,
        )
    else:
        logger.info(
            "[glm-asr] paper id=%d already linked to repository id=%d",
            paper.id,
            repo.id,
        )


def backfill_remaining_abstracts(db: Session) -> None:
    """Populate concise abstracts for the remaining HF-model external rows."""
    for source_url, abstract in REMAINING_ABSTRACTS.items():
        paper = (
            db.query(DBPaper)
            .filter(
                DBPaper.source == "external",
                DBPaper.source_url == source_url,
            )
            .first()
        )
        if paper is None:
            logger.warning("[abstracts] no external row for %s", source_url)
            continue
        if (paper.abstract or "").strip():
            logger.info(
                "[abstracts] paper id=%d (%s) already has an abstract; skipping",
                paper.id,
                source_url,
            )
            continue
        paper.abstract = abstract
        logger.info(
            "[abstracts] populated abstract for paper id=%d (%s)",
            paper.id,
            source_url,
        )


def backfill_asr_task_tags(db: Session) -> None:
    """Tag every paper with an ASR evaluation as `automatic-speech-recognition`.

    Uses `source='manual'` so that the auto keyword-matcher rebuild leaves
    these rows alone (the keyword matcher only deletes `source='auto'`
    rows when it re-runs).
    """
    asr_task = db.query(DBTask).filter(DBTask.slug == ASR_TASK_SLUG).first()
    if asr_task is None:
        logger.warning(
            "[asr-tags] task slug %r missing; skipping task backfill",
            ASR_TASK_SLUG,
        )
        return

    missing_ids = [
        row[0]
        for row in db.execute(
            text(
                """
                SELECT DISTINCT e.paper_id
                FROM evaluations e
                WHERE e.task_id = :tid
                  AND NOT EXISTS (
                      SELECT 1 FROM paper_tasks pt
                      WHERE pt.paper_id = e.paper_id AND pt.task_id = :tid
                  )
                """
            ),
            {"tid": asr_task.id},
        ).fetchall()
    ]

    if not missing_ids:
        logger.info("[asr-tags] every ASR-evaluated paper already tagged")
        return

    for pid in missing_ids:
        db.add(DBPaperTask(paper_id=pid, task_id=asr_task.id, source="manual"))
    db.flush()
    logger.info(
        "[asr-tags] tagged %d papers with task '%s'",
        len(missing_ids),
        ASR_TASK_SLUG,
    )


def report_coverage(db: Session) -> None:
    summary = (
        db.execute(
            text(
                """
            SELECT
              COUNT(*) AS total_external,
              COUNT(*) FILTER (WHERE abstract IS NULL OR btrim(abstract) = '')
                AS missing_abstract
            FROM papers
            WHERE source = 'external'
            """
            )
        )
        .mappings()
        .one()
    )
    logger.info(
        "External coverage: %d total, %d missing abstract",
        summary["total_external"],
        summary["missing_abstract"],
    )
    if summary["missing_abstract"]:
        rows = (
            db.execute(
                text(
                    """
                SELECT id, title, source_url
                FROM papers
                WHERE source = 'external'
                  AND (abstract IS NULL OR btrim(abstract) = '')
                ORDER BY id
                """
                )
            )
            .mappings()
            .all()
        )
        for row in rows:
            logger.warning(
                "  missing abstract: id=%s title=%r source_url=%s",
                row["id"],
                row["title"],
                row["source_url"],
            )

    asr_task_id = db.execute(
        text("SELECT id FROM tasks WHERE slug = :slug"),
        {"slug": ASR_TASK_SLUG},
    ).scalar()
    if asr_task_id is None:
        return
    asr_summary = (
        db.execute(
            text(
                """
            SELECT
              COUNT(DISTINCT paper_id) AS evaluated_papers,
              COUNT(DISTINCT paper_id) FILTER (
                  WHERE NOT EXISTS (
                      SELECT 1 FROM paper_tasks pt
                      WHERE pt.paper_id = e.paper_id AND pt.task_id = :tid
                  )
              ) AS missing_tags
            FROM evaluations e
            WHERE e.task_id = :tid
            """
            ),
            {"tid": asr_task_id},
        )
        .mappings()
        .one()
    )
    logger.info(
        "ASR task coverage: %d papers evaluated, %d missing task tag",
        asr_summary["evaluated_papers"],
        asr_summary["missing_tags"],
    )


def main() -> None:
    session = db_manager.session_local()
    try:
        consolidate_family(
            session,
            family_label="moonshine",
            canonical_url=MOONSHINE_CANONICAL_URL,
            variant_urls=MOONSHINE_HF_URLS,
            title=MOONSHINE_TITLE,
            abstract=MOONSHINE_ABSTRACT,
            hf_models=MOONSHINE_HF_URLS,
        )
        consolidate_family(
            session,
            family_label="niagara",
            canonical_url=NIAGARA_CANONICAL_URL,
            variant_urls=NIAGARA_HF_URLS,
            title=NIAGARA_TITLE,
            abstract=NIAGARA_ABSTRACT,
            hf_models=NIAGARA_HF_URLS,
        )
        relink_owsm_to_arxiv(session)
        link_glm_asr_repo(session)
        backfill_remaining_abstracts(session)
        backfill_asr_task_tags(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    session = db_manager.session_local()
    try:
        report_coverage(session)
    finally:
        session.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.exception("Cleanup failed: %s", exc)
        sys.exit(1)
