"""
Remove confidence intervals from evaluation results.

This script removes ± (plus-minus) symbols and everything after them from
metric values in evaluation results for a specific paper.

Usage:
    uv run --env-file backend/keys.env python scripts/remove_confidence_intervals.py 2010.11929
"""

import sys
from typing import Dict, Any
from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService


def clean_metric_value(value: Any) -> str:
    """
    Remove confidence intervals from a metric value.

    Examples:
        "89.0 ±4.8" -> "89.0"
        "78.8 ±3.6" -> "78.8"
        "95.2" -> "95.2"
    """
    if value is None:
        return None

    # Convert to string if not already
    value_str = str(value).strip()

    # Remove ± and everything after it
    if "±" in value_str:
        value_str = value_str.split("±")[0].strip()

    return value_str


def clean_metrics(metrics: Dict[str, Any]) -> Dict[str, str]:
    """Clean all metric values in a metrics dictionary."""
    if not metrics:
        return metrics

    cleaned = {}
    for key, value in metrics.items():
        cleaned[key] = clean_metric_value(value)

    return cleaned


def main():
    """Remove confidence intervals from evaluation results."""
    if len(sys.argv) < 2:
        print(
            "Usage: uv run --env-file backend/keys.env python scripts/remove_confidence_intervals.py <arxiv_id>"
        )
        sys.exit(1)

    arxiv_id = sys.argv[1]

    try:
        with db_manager.session_local() as db:
            # Get paper
            print(f"Looking up paper with ArXiv ID: {arxiv_id}...")
            paper_service = PaperService(db)
            try:
                paper = paper_service.get_paper_by_arxiv_id(arxiv_id)
                print(f"✓ Found paper: '{paper.title}' (ID={paper.id})")
                paper_id = int(paper.id)
            except Exception as e:
                print(f"✗ Error finding paper: {e}")
                sys.exit(1)

            # Get all evaluations for this paper
            print(f"\nFetching evaluations for paper ID {paper_id}...")
            evaluation_service = EvaluationService(db)
            evaluations_result = evaluation_service.get_evaluations(
                paper_id=paper_id,
                page_size=1000,  # Get all evaluations
            )

            evaluations = evaluations_result.results
            print(f"✓ Found {len(evaluations)} evaluations")

            if len(evaluations) == 0:
                print("No evaluations to update.")
                sys.exit(0)

            # Process each evaluation
            updated_count = 0
            for eval_obj in evaluations:
                original_metrics = eval_obj.metrics
                if not original_metrics:
                    continue

                # Check if any metric has confidence intervals
                has_intervals = False
                for value in original_metrics.values():
                    if value and isinstance(value, str) and "±" in str(value):
                        has_intervals = True
                        break

                if not has_intervals:
                    continue

                # Clean the metrics
                cleaned_metrics = clean_metrics(original_metrics)

                # Show what we're updating
                print(f"\n  Evaluation ID {eval_obj.id}:")
                print(f"    Task: {eval_obj.task_name}")
                print(f"    Dataset: {eval_obj.dataset_name}")
                print(f"    Model: {eval_obj.model_name or 'N/A'}")
                print(f"    Before: {original_metrics}")
                print(f"    After:  {cleaned_metrics}")

                # Update the evaluation
                try:
                    evaluation_service.update_evaluation(
                        evaluation_id=int(eval_obj.id),
                        metrics=cleaned_metrics,
                    )
                    print("    ✓ Updated successfully")
                    updated_count += 1
                except Exception as e:
                    print(f"    ✗ Error updating: {e}")

            print(f"\n{'=' * 80}")
            print(
                f"Summary: Updated {updated_count} out of {len(evaluations)} evaluations"
            )
            print(f"{'=' * 80}")

    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
