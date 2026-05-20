"""
Add the HuggingFaceBio DNA benchmarks collection to the Biology task.

Collection: https://huggingface.co/collections/HuggingFaceBio/dna-benchmarks
Benchmarks:
  1. HuggingFaceBio/genomic-niah   -> source paper: RULER (arXiv 2404.06654)
  2. GenerTeam/sequence-recovery   -> source paper: GENERator (arXiv 2502.07272)
  3. HuggingFaceBio/clinvar-vep    -> source paper: GPN-MSA (Nature Biotech 2024,
                                                   no arXiv -> external row)
  4. HuggingFaceBio/perturbation-bench -> no formal source paper, attribute to
                                          the Carbon GitHub repo (external row)
  5. HuggingFaceBio/traitgym       -> source paper: TraitGym (bioRxiv 2025,
                                                   no arXiv -> external row)

For each benchmark this script:
  - Ensures the source paper row exists (arXiv rows looked up by arxiv_id;
    external rows created idempotently by source_url).
  - Inserts or updates the dataset row (slug-keyed).
  - Links the dataset to the Biology task in `task_datasets` with a
    `featured_rank` so it shows up in the task's default order.
  - Links the dataset to the `Accuracy` metric via `task_dataset_metrics`.

Idempotent: safe to re-run.

Run:
    uv run --env-file backend/keys.env python scripts/add_biology_dna_benchmarks.py
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.database import (
    Dataset as DBDataset,
    Paper as DBPaper,
    Task as DBTask,
    TaskDataset as DBTaskDataset,
    TaskDatasetMetric as DBTaskDatasetMetric,
    Metric as DBMetric,
)
from backend.utils.slug_utils import slugify


SITE_DOMAIN = "paperswithcode.co"
BIOLOGY_SLUG = "biology"
ACCURACY_METRIC_NAME = "Accuracy"


def native_paper_url(paper: DBPaper) -> str:
    """Native paperswithcode.co paper URL — uses arxiv_id when available."""
    identifier = paper.arxiv_id if paper.arxiv_id else str(paper.id)
    return f"https://{SITE_DOMAIN}/paper/{identifier}"


def ensure_arxiv_paper(db: Session, arxiv_id: str) -> DBPaper:
    paper = db.query(DBPaper).filter(DBPaper.arxiv_id == arxiv_id).first()
    if not paper:
        raise RuntimeError(
            f"ArXiv paper {arxiv_id} not found locally — import it first"
        )
    return paper


def ensure_external_paper(
    db: Session,
    *,
    source_url: str,
    title: str,
    abstract: Optional[str] = None,
    date_published: Optional[date] = None,
) -> DBPaper:
    paper = (
        db.query(DBPaper)
        .filter(DBPaper.source == "external", DBPaper.source_url == source_url)
        .first()
    )
    if paper:
        changed = False
        if paper.title != title:
            paper.title = title
            changed = True
        if abstract and paper.abstract != abstract:
            paper.abstract = abstract
            changed = True
        if date_published and paper.date_published != date_published:
            paper.date_published = date_published
            changed = True
        if changed:
            db.flush()
        return paper

    paper = DBPaper(
        source="external",
        source_url=source_url,
        title=title,
        abstract=abstract,
        date_published=date_published,
        arxiv_id=None,
        version="v1",
        is_latest_version=True,
    )
    db.add(paper)
    db.flush()
    return paper


def upsert_dataset(
    db: Session,
    *,
    name: str,
    slug: str,
    description: str,
    hf_url: str,
    url: Optional[str],
    paper: Optional[DBPaper],
    license_name: Optional[str] = "Apache 2.0",
    modalities: Optional[list[str]] = None,
) -> DBDataset:
    """Insert the dataset if missing; otherwise update key fields."""
    dataset = db.query(DBDataset).filter(DBDataset.slug == slug).first()

    paper_id = paper.id if paper else None
    paper_title = paper.title if paper else None
    paper_url = native_paper_url(paper) if paper else None

    if not dataset:
        dataset = DBDataset(
            name=name,
            slug=slug,
            description=description,
            hf_url=hf_url,
            url=url,
            introducing_paper_id=paper_id,
            introducing_paper_title=paper_title,
            paper_url=paper_url,
            license_name=license_name,
            modalities=modalities,
        )
        db.add(dataset)
        db.flush()
        return dataset

    dataset.name = name
    dataset.description = description
    dataset.hf_url = hf_url
    if url is not None:
        dataset.url = url
    dataset.introducing_paper_id = paper_id
    dataset.introducing_paper_title = paper_title
    dataset.paper_url = paper_url
    if license_name:
        dataset.license_name = license_name
    if modalities:
        dataset.modalities = modalities
    db.flush()
    return dataset


def link_task_dataset(
    db: Session, *, task_id: int, dataset_id: int, featured_rank: int
) -> None:
    row = (
        db.query(DBTaskDataset)
        .filter(
            DBTaskDataset.task_id == task_id,
            DBTaskDataset.dataset_id == dataset_id,
        )
        .first()
    )
    if not row:
        db.add(
            DBTaskDataset(
                task_id=task_id,
                dataset_id=dataset_id,
                featured_rank=featured_rank,
            )
        )
        db.flush()
        return
    if row.featured_rank != featured_rank:
        row.featured_rank = featured_rank
        db.flush()


def link_metric(db: Session, *, task_id: int, dataset_id: int, metric_id: int) -> None:
    row = (
        db.query(DBTaskDatasetMetric)
        .filter(
            DBTaskDatasetMetric.task_id == task_id,
            DBTaskDatasetMetric.dataset_id == dataset_id,
            DBTaskDatasetMetric.metric_id == metric_id,
        )
        .first()
    )
    if row:
        return
    db.add(
        DBTaskDatasetMetric(task_id=task_id, dataset_id=dataset_id, metric_id=metric_id)
    )
    db.flush()


def main() -> int:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        biology = db.query(DBTask).filter(DBTask.slug == BIOLOGY_SLUG).one_or_none()
        if not biology:
            raise RuntimeError("Biology task is missing — run the migration first")

        accuracy = (
            db.query(DBMetric).filter(DBMetric.name == ACCURACY_METRIC_NAME).one()
        )

        # Source papers --------------------------------------------------------
        ruler = ensure_arxiv_paper(db, "2404.06654")
        generator = ensure_arxiv_paper(db, "2502.07272")

        gpn_msa = ensure_external_paper(
            db,
            source_url="https://www.nature.com/articles/s41587-024-02511-w",
            title=(
                "A DNA language model based on multispecies alignment predicts "
                "the effects of genome-wide variants"
            ),
            abstract=(
                "GPN-MSA is an alignment-based DNA language model that uses "
                "whole-genome multiple sequence alignments to predict the "
                "deleteriousness of single-nucleotide variants across the human "
                "genome. The model is trained on multi-species alignments and "
                "evaluated on clinical, experimental, and population-genomic "
                "benchmarks including ClinVar, COSMIC, OMIM, deep mutational "
                "scanning assays, DepMap, and gnomAD."
            ),
            date_published=date(2024, 12, 30),
        )
        traitgym = ensure_external_paper(
            db,
            source_url=("https://www.biorxiv.org/content/10.1101/2025.02.11.637758v1"),
            title=(
                "Benchmarking DNA Sequence Models for Causal Regulatory Variant "
                "Prediction in Human Genetics"
            ),
            abstract=(
                "TraitGym is a benchmark of putative causal regulatory variants "
                "across Mendelian and complex traits, designed to evaluate DNA "
                "sequence models on variant effect prediction. The benchmark "
                "comprises 338 putative causal non-coding variants from 113 "
                "Mendelian diseases and 1,140 putative causal variants from 83 "
                "polygenic UK Biobank traits, each matched 9:1 against controls."
            ),
            date_published=date(2025, 2, 11),
        )
        carbon = ensure_external_paper(
            db,
            source_url="https://github.com/huggingface/carbon",
            title="Carbon: Genomic Language Models",
            abstract=(
                "Carbon is a family of DNA language models released by Hugging "
                "Face for long-range genomic sequence modeling, including "
                "Carbon-3B and Carbon-8B. The release ships with a set of "
                "zero-shot evaluation benchmarks (Genomic-NIAH, ClinVar VEP, "
                "Perturbation Bench, TraitGym) covering long-context retrieval, "
                "variant effect prediction, and sequence-level perturbation "
                "tasks. The Perturbation Bench tasks in particular originate "
                "with this release."
            ),
            date_published=None,
        )

        # Datasets -------------------------------------------------------------
        DNA_TEXT = ["Text"]

        genomic_niah = upsert_dataset(
            db,
            name="Genomic-NIAH",
            slug=slugify("Genomic-NIAH"),
            description=(
                "Genomic-NIAH is a long-context retrieval benchmark for genomic "
                "language models, inspired by NIAH and RULER from the NLP "
                "literature. Each example plants a random (KEY, VALUE) DNA pair "
                "inside a real-genome haystack and asks the model to recover "
                "VALUE given the haystack followed by KEY. The benchmark spans "
                "4 retrieval tasks of increasing difficulty (plain retrieval "
                "plus three near-duplicate variants) and 6 context lengths from "
                "4k to 128k 6-mer tokens (≈ 24 kbp to 786 kbp), for a total of "
                "24 sub-configurations of 500 examples each (12,000 retrieval "
                "examples)."
            ),
            hf_url="https://huggingface.co/datasets/HuggingFaceBio/genomic-niah",
            url=None,
            paper=ruler,
            modalities=DNA_TEXT,
        )
        sequence_recovery = upsert_dataset(
            db,
            name="Sequence Recovery",
            slug=slugify("Sequence Recovery"),
            description=(
                "Sequence Recovery (also called Next K-mer Prediction) is a "
                "zero-shot evaluation method introduced in the GENERator paper "
                "to assess the quality of pretrained genomic models. Given an "
                "input DNA sequence of up to 96k base pairs, the model predicts "
                "the next 128 bp and the prediction is scored against the "
                "ground truth. The dataset provides three subsets (eukaryote, "
                "bacteria, and others) for a total of 80,205 rows."
            ),
            hf_url="https://huggingface.co/datasets/GenerTeam/sequence-recovery",
            url=None,
            paper=generator,
            modalities=DNA_TEXT,
        )
        clinvar_vep = upsert_dataset(
            db,
            name="ClinVar VEP",
            slug=slugify("ClinVar VEP"),
            description=(
                "ClinVar VEP is a clinical variant-effect-prediction benchmark "
                "for DNA language models, with two balanced binary "
                "classification subsets: coding (39,473 variants — 17,231 "
                "benign vs 22,242 pathogenic, exonic protein-coding regions) "
                "and non-coding (15,258 variants — 7,629 benign vs 7,629 "
                "pathogenic, intronic + 5'/3' UTR). The coding subset reuses "
                "the ClinVar split from the GPN-MSA study; the non-coding "
                "subset is constructed from the original ClinVar VCF by the "
                "HuggingFaceBio team to provide a clean, balanced non-coding "
                "evaluation."
            ),
            hf_url="https://huggingface.co/datasets/HuggingFaceBio/clinvar-vep",
            url=None,
            paper=gpn_msa,
            modalities=DNA_TEXT,
        )
        perturbation_bench = upsert_dataset(
            db,
            name="Perturbation Bench",
            slug=slugify("Perturbation Bench"),
            description=(
                "Perturbation Bench is a sequence-level perturbation benchmark "
                "for DNA foundation models. Each task presents pairs of "
                "genomic sequences — one real (unperturbed) and one "
                "structurally altered — and measures pairwise discrimination "
                "accuracy (does the model assign higher log-likelihood to the "
                "original?). The benchmark ships three configurations: "
                "synonymous codon substitution in human CDS (20,000 pairs), "
                "synonymous codon substitution in mouse CDS (20,000 pairs), "
                "and CAG repeat insertion in human CDS (20,000 pairs)."
            ),
            hf_url=(
                "https://huggingface.co/datasets/HuggingFaceBio/perturbation-bench"
            ),
            url=None,
            paper=carbon,
            modalities=DNA_TEXT,
        )
        traitgym_ds = upsert_dataset(
            db,
            name="TraitGym",
            slug=slugify("TraitGym"),
            description=(
                "TraitGym is a benchmark of putative causal regulatory "
                "variants for evaluating DNA sequence models on variant effect "
                "prediction. It consists of two configurations: mendelian "
                "traits (3,380 variants from 113 monogenic Mendelian diseases) "
                "and complex traits (11,400 variants from 83 polygenic UK "
                "Biobank traits, fine-mapped with PIP > 0.9), each matched 9:1 "
                "against controls. The HuggingFaceBio repackaging additionally "
                "pre-extracts the 8,192 bp window centered on each variant."
            ),
            hf_url="https://huggingface.co/datasets/HuggingFaceBio/traitgym",
            url=None,
            paper=traitgym,
            modalities=DNA_TEXT,
        )

        # Task linkage with featured rank --------------------------------------
        ranked_datasets = [
            genomic_niah,
            sequence_recovery,
            clinvar_vep,
            perturbation_bench,
            traitgym_ds,
        ]
        for rank, ds in enumerate(ranked_datasets, start=1):
            link_task_dataset(
                db, task_id=biology.id, dataset_id=ds.id, featured_rank=rank
            )
            link_metric(
                db,
                task_id=biology.id,
                dataset_id=ds.id,
                metric_id=accuracy.id,
            )

        db.commit()

        print(
            f"Biology task ({biology.id}) now has "
            f"{len(ranked_datasets)} ranked benchmarks linked to "
            f"'{accuracy.name}'."
        )
        for rank, ds in enumerate(ranked_datasets, start=1):
            paper_url = ds.paper_url or "(no paper)"
            print(
                f"  rank={rank} id={ds.id} slug={ds.slug:<22s} "
                f"introducing_paper_id={ds.introducing_paper_id} "
                f"paper_url={paper_url}"
            )

        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
