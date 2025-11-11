#!/usr/bin/env python3
"""
Add GPQA dataset and evaluation result for paper 2508.06471.

Usage:
    uv run --env-file backend/keys.env scripts/add_gpqa_evaluation.py
"""

from backend.database.connection import db_manager
from backend.services.dataset_service import DatasetService
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService
from backend.models.api import DatasetCreateRequest
from sqlalchemy.orm import Session


def main():
    arxiv_id = "2508.06471"

    session: Session = db_manager.session_local()
    try:
        # Get paper
        paper_service = PaperService(session)
        paper = paper_service.get_paper_by_arxiv_id(arxiv_id)
        paper_id = int(paper.id)
        print(f"Found paper: ID={paper_id}, Title={paper.title}")

        # Check if GPQA dataset already exists
        dataset_service = DatasetService(session)
        gpqa_datasets = dataset_service.get_datasets(search="GPQA", page_size=10)

        gpqa_dataset = None
        for ds in gpqa_datasets.results:
            if ds.name == "GPQA" and "Diamond" not in ds.name:
                gpqa_dataset = ds
                break

        if gpqa_dataset:
            print(
                f"GPQA dataset already exists: ID={gpqa_dataset.id}, Name={gpqa_dataset.name}"
            )
            dataset_id = int(gpqa_dataset.id)
        else:
            # Create GPQA dataset
            print("\nCreating GPQA dataset...")
            dataset_request = DatasetCreateRequest(
                name="GPQA",
                full_name="GPQA: Graduate-Level Google-Proof Q&A Benchmark",
                description="GPQA science QA benchmark; reported as Avg@8 in the paper.",
                task_ids=[5],  # Language Modeling task
            )

            gpqa_dataset = dataset_service.create_dataset(dataset_request)
            dataset_id = int(gpqa_dataset.id)
            print(f"Created GPQA dataset: ID={dataset_id}, Slug={gpqa_dataset.slug}")

        # Check if evaluation already exists
        evaluation_service = EvaluationService(session)
        existing_evals = evaluation_service.get_evaluations(
            paper_id=paper_id, dataset_id=dataset_id, page_size=100
        )

        # Check for existing evaluation with this model and metric
        model_name = "GLM-4.5 (355B)"
        best_metric = "Accuracy"

        for eval_obj in existing_evals.results:
            if (
                eval_obj.model_name == model_name
                and eval_obj.best_metric == best_metric
            ):
                print(f"\nEvaluation already exists: ID={eval_obj.id}")
                print(f"  Model: {eval_obj.model_name}")
                print(f"  Dataset: {eval_obj.dataset_name}")
                print(f"  Best Metric: {eval_obj.best_metric}")
                print(f"  Metrics: {eval_obj.metrics}")
                return

        # Add evaluation result
        print("\nAdding evaluation result...")
        evaluation = evaluation_service.create_evaluation(
            paper_id=paper_id,
            task_id=5,  # Language Modeling
            dataset_id=dataset_id,
            model_name=model_name,
            metrics={"Accuracy": "79.1"},
            best_metric="Accuracy",
        )
        print("\n✓ Successfully added evaluation:")
        print(f"  Evaluation ID: {evaluation.id}")
        print(f"  Model: {evaluation.model_name}")
        print(f"  Dataset: {evaluation.dataset_name}")
        print(f"  Best Metric: {evaluation.best_metric}")
        print(f"  Metrics: {evaluation.metrics}")
        print(f"  Best Rank: {evaluation.best_rank}")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
    finally:
        session.close()


if __name__ == "__main__":
    main()
