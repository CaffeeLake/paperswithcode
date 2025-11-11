"""
Find datasets in the database that have evaluations but are missing descriptions, paper URLs, or HF URLs.
"""

from backend.database.connection import db_manager
from backend.models.database import Dataset, Evaluation
from sqlalchemy import func, or_


def find_datasets_missing_info():
    """Find datasets with evaluations that are missing key information."""
    with db_manager.session_local() as db:
        # Query datasets that have at least one evaluation
        # and are missing description, paper_url, or hf_url
        datasets_with_evals = (
            db.query(Dataset)
            .join(Evaluation, Dataset.id == Evaluation.dataset_id)
            .filter(
                or_(
                    Dataset.description is None,
                    Dataset.description == "",
                    Dataset.paper_url is None,
                    Dataset.paper_url == "",
                    Dataset.hf_url is None,
                    Dataset.hf_url == "",
                )
            )
            .group_by(Dataset.id)
            .order_by(
                func.count(Evaluation.id).desc()
            )  # Order by number of evaluations
            .all()
        )

        print(
            f"Found {len(datasets_with_evals)} datasets with evaluations that are missing information:\n"
        )
        print(f"{'ID':<6} {'Name':<40} {'Evals':<7} {'Desc':<6} {'Paper':<7} {'HF':<4}")
        print("=" * 80)

        results = []
        for dataset in datasets_with_evals:
            eval_count = (
                db.query(func.count(Evaluation.id))
                .filter(Evaluation.dataset_id == dataset.id)
                .scalar()
            )

            has_desc = bool(dataset.description and dataset.description.strip())
            has_paper = bool(dataset.paper_url and dataset.paper_url.strip())
            has_hf = bool(dataset.hf_url and dataset.hf_url.strip())

            desc_status = "✓" if has_desc else "✗"
            paper_status = "✓" if has_paper else "✗"
            hf_status = "✓" if has_hf else "✗"

            print(
                f"{dataset.id:<6} {dataset.name[:38]:<40} {eval_count:<7} {desc_status:<6} {paper_status:<7} {hf_status:<4}"
            )

            results.append(
                {
                    "id": dataset.id,
                    "name": dataset.name,
                    "slug": dataset.slug,
                    "eval_count": eval_count,
                    "has_description": has_desc,
                    "has_paper_url": has_paper,
                    "has_hf_url": has_hf,
                    "description": dataset.description,
                    "paper_url": dataset.paper_url,
                    "hf_url": dataset.hf_url,
                    "url": dataset.url,
                    "full_name": dataset.full_name,
                }
            )

        return results


if __name__ == "__main__":
    results = find_datasets_missing_info()

    print(f"\n{'=' * 80}")
    print("Summary:")
    print(f"{'=' * 80}")

    missing_desc = sum(1 for r in results if not r["has_description"])
    missing_paper = sum(1 for r in results if not r["has_paper_url"])
    missing_hf = sum(1 for r in results if not r["has_hf_url"])

    print(f"Total datasets: {len(results)}")
    print(f"Missing description: {missing_desc}")
    print(f"Missing paper URL: {missing_paper}")
    print(f"Missing HF URL: {missing_hf}")
