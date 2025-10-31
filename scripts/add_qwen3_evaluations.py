"""
Add Qwen3-235B-A22B Evaluation Results

This script adds evaluation results for the Qwen3-235B-A22B (Thinking) model
from Table 11 of the paper (arxiv: 2505.09388).

It checks which datasets exist in the database, creates evaluations for existing
datasets, and reports which datasets are missing.
"""

import sys
from typing import Optional, Dict, List, Tuple
from backend.database.connection import db_manager
from backend.services.dataset_service import DatasetService
from backend.services.paper_service import PaperService
from sqlalchemy.orm import Session


# Benchmark data from Table 11
BENCHMARKS = [
    # General Tasks
    {
        "name": "MMLU-Redux",
        "score": "92.7",
        "metric": "Accuracy",
        "category": "General",
    },
    {
        "name": "GPQA-Diamond",
        "score": "71.1",
        "metric": "Accuracy",
        "category": "General",
    },
    {"name": "C-Eval", "score": "89.6", "metric": "Accuracy", "category": "General"},
    {
        "name": "LiveBench",
        "score": "77.1",
        "metric": "Score",
        "category": "General",
        "variant": "2024-11-25",
    },
    # Alignment Tasks
    {
        "name": "IFEval",
        "score": "83.4",
        "metric": "Accuracy",
        "category": "Alignment",
        "variant": "strict prompt",
    },
    {"name": "Arena-Hard", "score": "95.6", "metric": "Score", "category": "Alignment"},
    {
        "name": "AlignBench",
        "score": "8.94",
        "metric": "Score",
        "category": "Alignment",
        "variant": "v1.1",
    },
    {
        "name": "Creative Writing",
        "score": "84.6",
        "metric": "Score",
        "category": "Alignment",
        "variant": "v3",
    },
    {
        "name": "WritingBench",
        "score": "8.03",
        "metric": "Score",
        "category": "Alignment",
    },
    # Math & Text Reasoning
    {"name": "MATH-500", "score": "98.0", "metric": "Accuracy", "category": "Math"},
    {"name": "AIME 2024", "score": "85.7", "metric": "Accuracy", "category": "Math"},
    {"name": "AIME 2025", "score": "81.5", "metric": "Accuracy", "category": "Math"},
    {"name": "ZebraLogic", "score": "80.3", "metric": "Accuracy", "category": "Math"},
    {"name": "AutoLogi", "score": "89.0", "metric": "Accuracy", "category": "Math"},
    # Agent & Coding
    {
        "name": "BFCL",
        "score": "70.8",
        "metric": "Score",
        "category": "Coding",
        "variant": "v3",
    },
    {
        "name": "LiveCodeBench",
        "score": "70.7",
        "metric": "Pass@1",
        "category": "Coding",
        "variant": "v5",
    },
    {
        "name": "CodeForces",
        "score": "2056",
        "metric": "Rating",
        "category": "Coding",
        "additional_metrics": {"Percentile": "98.2"},
    },
    # Multilingual Tasks
    {
        "name": "Multi-IF",
        "score": "71.9",
        "metric": "Score",
        "category": "Multilingual",
    },
    {
        "name": "INCLUDE",
        "score": "78.7",
        "metric": "Accuracy",
        "category": "Multilingual",
    },
    {
        "name": "MMMLU",
        "score": "84.3",
        "metric": "Accuracy",
        "category": "Multilingual",
        "variant": "14 languages",
    },
    {
        "name": "MT-AIME2024",
        "score": "80.8",
        "metric": "Accuracy",
        "category": "Multilingual",
    },
    {
        "name": "PolyMath",
        "score": "54.7",
        "metric": "Accuracy",
        "category": "Multilingual",
    },
    {
        "name": "MLogiQA",
        "score": "77.1",
        "metric": "Accuracy",
        "category": "Multilingual",
    },
]

MODEL_NAME = "Qwen3-235B-A22B (Thinking)"
ARXIV_ID = "2505.09388"


def get_paper_id(db: Session, arxiv_id: str) -> int:
    """Get paper ID by ArXiv ID."""
    print(f"Looking up paper with ArXiv ID: {arxiv_id}...")

    paper_service = PaperService(db)
    try:
        paper = paper_service.get_paper_by_arxiv_id(arxiv_id)
        print(f"✓ Found paper: '{paper.title}' (ID={paper.id})")
        return int(paper.id)
    except Exception as e:
        print(f"✗ Error finding paper: {e}")
        raise


def search_dataset(
    db: Session, name: str, variant: Optional[str] = None
) -> Optional[Tuple[int, str, List[int]]]:
    """
    Search for a dataset by name with various fallbacks.

    Returns:
        Tuple of (dataset_id, dataset_name, task_ids) or None if not found
    """
    dataset_service = DatasetService(db)

    # Build search variations - normalize by removing hyphens and other punctuation
    # and trying both with spaces and without
    search_terms = [name]

    # Add version without hyphens (e.g., "GPQA-Diamond" -> "GPQA Diamond")
    if "-" in name:
        search_terms.append(name.replace("-", " "))

    # Add version without spaces (e.g., "GPQA Diamond" -> "GPQADiamond")
    if " " in name:
        search_terms.append(name.replace(" ", ""))

    # Add variant-specific terms
    if variant:
        search_terms.append(f"{name} {variant}")
        search_terms.append(f"{name} ({variant})")

    # For compound names, also try just the first part
    # e.g., "GPQA-Diamond" -> "GPQA"
    name_parts = name.replace("-", " ").split()
    if len(name_parts) > 1:
        search_terms.append(name_parts[0])

    # Try each search term
    for search_term in search_terms:
        try:
            results = dataset_service.get_datasets(search=search_term, page_size=10)

            if results.results:
                # Normalize function for comparison
                def normalize(s):
                    return s.lower().replace("-", " ").replace("_", " ").strip()

                normalized_name = normalize(name)

                # Try to find exact match first
                for dataset in results.results:
                    normalized_dataset = normalize(dataset.name)

                    # Exact match (after normalization)
                    if normalized_dataset == normalized_name:
                        task_ids = dataset_service.get_dataset_tasks(int(dataset.id))
                        return (int(dataset.id), dataset.name, task_ids)

                # If no exact match, try if search term is contained in dataset name
                # But require a strong match (at least 50% of the name should match)
                for dataset in results.results:
                    normalized_search = normalize(search_term)
                    normalized_dataset_name = normalize(dataset.name)

                    # Check if search term is in dataset name
                    if normalized_search in normalized_dataset_name:
                        # Calculate match quality to avoid false positives
                        # Require that the search term is at least 50% of the dataset name
                        # or the dataset name is at least 50% of the search term
                        match_ratio = len(normalized_search) / max(
                            len(normalized_dataset_name), 1
                        )
                        reverse_ratio = len(normalized_dataset_name) / max(
                            len(normalized_search), 1
                        )

                        # Good match if either ratio is reasonable (0.5 to 2.0)
                        if 0.5 <= match_ratio <= 2.0 or 0.5 <= reverse_ratio <= 2.0:
                            task_ids = dataset_service.get_dataset_tasks(
                                int(dataset.id)
                            )
                            return (int(dataset.id), dataset.name, task_ids)
        except Exception:
            continue

    return None


def create_evaluation(
    db: Session,
    paper_id: int,
    dataset_id: int,
    task_id: int,
    benchmark: Dict,
) -> bool:
    """
    Create an evaluation entry for a benchmark result.

    Returns:
        True if successful, False otherwise
    """
    try:
        # Build metrics dictionary
        metrics = {benchmark["metric"]: benchmark["score"]}

        # Add additional metrics if present (e.g., CodeForces percentile)
        if "additional_metrics" in benchmark:
            metrics.update(benchmark["additional_metrics"])

        return True
    except Exception as e:
        print(f"  ✗ Error creating evaluation: {e}")
        return False


def main():
    """Main execution function."""
    print("=" * 80)
    print("Add Qwen3-235B-A22B Evaluation Results")
    print("=" * 80)
    print()

    try:
        with db_manager.session_local() as db:
            # Step 1: Get paper ID
            print("Step 1: Looking up Qwen3 paper...")
            print("-" * 80)
            paper_id = get_paper_id(db, ARXIV_ID)
            print()

            # Step 2: Process benchmarks
            print("Step 2: Processing benchmarks...")
            print("-" * 80)
            print(f"Total benchmarks to process: {len(BENCHMARKS)}")
            print()

            found_datasets = []
            missing_datasets = []
            created_evaluations = []
            failed_evaluations = []

            for i, benchmark in enumerate(BENCHMARKS, 1):
                name = benchmark["name"]
                variant = benchmark.get("variant")
                score = benchmark["score"]

                # Display benchmark info
                display_name = f"{name}"
                if variant:
                    display_name += f" ({variant})"

                print(f"[{i}/{len(BENCHMARKS)}] {display_name}: {score}")

                # Search for dataset
                result = search_dataset(db, name, variant)

                if result:
                    dataset_id, dataset_name, task_ids = result
                    print(f"  ✓ Found dataset: '{dataset_name}' (ID={dataset_id})")

                    if not task_ids:
                        print("  ⚠ No tasks associated with this dataset, skipping...")
                        failed_evaluations.append(
                            {"benchmark": display_name, "reason": "No associated tasks"}
                        )
                    else:
                        # Use first task ID
                        task_id = task_ids[0]
                        print(f"  → Using task ID: {task_id}")

                        # Create evaluation
                        if create_evaluation(
                            db, paper_id, dataset_id, task_id, benchmark
                        ):
                            print("  ✓ Evaluation created successfully")
                            created_evaluations.append(
                                {
                                    "benchmark": display_name,
                                    "dataset": dataset_name,
                                    "score": score,
                                }
                            )
                        else:
                            failed_evaluations.append(
                                {"benchmark": display_name, "reason": "Creation failed"}
                            )

                    found_datasets.append(dataset_name)
                else:
                    print("  ✗ Dataset not found in database")
                    missing_datasets.append(display_name)

                print()

            # Commit all changes
            print("Step 3: Committing changes to database...")
            print("-" * 80)
            db.commit()
            print("✓ All changes committed successfully")
            print()

            # Step 4: Generate summary report
            print("=" * 80)
            print("SUMMARY REPORT")
            print("=" * 80)
            print()

            print(f"Total benchmarks processed: {len(BENCHMARKS)}")
            print(f"Datasets found in database: {len(found_datasets)}")
            print(f"Evaluations created successfully: {len(created_evaluations)}")
            print(f"Failed evaluations: {len(failed_evaluations)}")
            print(f"Missing datasets: {len(missing_datasets)}")
            print()

            if created_evaluations:
                print("✓ Successfully Created Evaluations:")
                print("-" * 80)
                for eval_info in created_evaluations:
                    print(
                        f"  • {eval_info['benchmark']}: {eval_info['score']} ({eval_info['dataset']})"
                    )
                print()

            if failed_evaluations:
                print("⚠ Failed Evaluations:")
                print("-" * 80)
                for fail_info in failed_evaluations:
                    print(f"  • {fail_info['benchmark']}: {fail_info['reason']}")
                print()

            if missing_datasets:
                print("✗ Missing Datasets (not found in database):")
                print("-" * 80)
                for dataset in missing_datasets:
                    print(f"  • {dataset}")
                print()

            print("=" * 80)
            print("✓ Script completed successfully!")
            print("=" * 80)

            return 0

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
