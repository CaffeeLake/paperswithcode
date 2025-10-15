"""
Fix benchmark leaderboard issues:
1. Remove CoDETR evaluation with score 0
2. Verify evaluation data integrity
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.config import get_settings
from backend.models.database import Evaluation as DBEvaluation


def main():
    settings = get_settings()
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Find CoDETR evaluations
        print("🔍 Finding CoDETR evaluations...")
        codetr_evals = (
            session.query(DBEvaluation)
            .filter(DBEvaluation.model_name.ilike("%codetr%"))
            .all()
        )

        print(f"Found {len(codetr_evals)} CoDETR evaluations:")
        for eval in codetr_evals:
            print(
                f"  ID: {eval.id}, Model: {eval.model_name}, Metrics: {eval.metrics}, Best Metric: {eval.best_metric}"
            )

            # Check if any metric value is 0
            if eval.metrics and eval.best_metric:
                metric_value = eval.metrics.get(eval.best_metric, 0)
                print(f"    {eval.best_metric}: {metric_value}")

                if metric_value == 0 or metric_value == "0":
                    print("    ⚠️  Found evaluation with score 0!")
                    confirm = input(f"    Delete evaluation ID {eval.id}? (yes/no): ")
                    if confirm.lower() == "yes":
                        session.delete(eval)
                        print(f"    ✅ Deleted evaluation ID {eval.id}")

        # Find all evaluations with 0 scores in any metric
        print("\n🔍 Finding all evaluations with 0 scores...")
        all_evals = session.query(DBEvaluation).all()
        zero_score_evals = []

        for eval in all_evals:
            if eval.metrics and eval.best_metric:
                metric_value = eval.metrics.get(eval.best_metric, 0)
                try:
                    if float(metric_value) == 0:
                        zero_score_evals.append(eval)
                except (ValueError, TypeError):
                    pass

        if zero_score_evals:
            print(f"Found {len(zero_score_evals)} evaluations with 0 scores:")
            for eval in zero_score_evals:
                print(
                    f"  ID: {eval.id}, Model: {eval.model_name}, Metric: {eval.best_metric}, Value: {eval.metrics.get(eval.best_metric)}"
                )

            confirm = input(
                f"\nDelete all {len(zero_score_evals)} evaluations with 0 scores? (yes/no): "
            )
            if confirm.lower() == "yes":
                for eval in zero_score_evals:
                    session.delete(eval)
                print(f"✅ Deleted {len(zero_score_evals)} evaluations")
        else:
            print("✅ No evaluations with 0 scores found")

        session.commit()
        print("\n✅ Database updated successfully")

    except Exception as e:
        print(f"❌ Error: {e}")
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    main()
