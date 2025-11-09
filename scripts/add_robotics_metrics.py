"""
Add missing robotics metrics to the database.

This script adds metrics needed for robot manipulation benchmarks:
- Average Length (for CALVIN benchmark)
- Success Rate (if not exists, case-sensitive version)
"""

from backend.database.connection import db_manager
from backend.models.database import Metric


def add_robotics_metrics():
    """Add missing robotics metrics."""
    with db_manager.session_local() as db:
        # Check for "Average Length"
        avg_length = db.query(Metric).filter(Metric.name == "Average Length").first()
        if not avg_length:
            print("Adding 'Average Length' metric...")
            avg_length = Metric(
                name="Average Length",
                description="Average number of successfully completed sub-tasks in a sequence (used in CALVIN benchmark)",
                direction="higher_is_better",
            )
            db.add(avg_length)
            db.commit()
            print(f"✓ Added 'Average Length' metric (ID: {avg_length.id})")
        else:
            print(f"'Average Length' metric already exists (ID: {avg_length.id})")

        # Check for "Success Rate" (capital R)
        success_rate_capital = (
            db.query(Metric).filter(Metric.name == "Success Rate").first()
        )
        success_rate_lower = (
            db.query(Metric).filter(Metric.name == "Success rate").first()
        )

        if success_rate_lower and not success_rate_capital:
            # Update to use capital R for consistency
            print("Updating 'Success rate' to 'Success Rate' for consistency...")
            success_rate_lower.name = "Success Rate"
            db.commit()
            print(f"✓ Updated metric name (ID: {success_rate_lower.id})")
        elif success_rate_capital:
            print(
                f"'Success Rate' metric already exists (ID: {success_rate_capital.id})"
            )
        elif not success_rate_lower and not success_rate_capital:
            print("Adding 'Success Rate' metric...")
            success_rate = Metric(
                name="Success Rate",
                description="Percentage of successful task completions in robot manipulation benchmarks",
                direction="higher_is_better",
            )
            db.add(success_rate)
            db.commit()
            print(f"✓ Added 'Success Rate' metric (ID: {success_rate.id})")

        # Show all robotics-related metrics
        print("\n=== Robotics-related metrics ===")
        metrics = (
            db.query(Metric)
            .filter(
                Metric.name.in_(
                    ["Success Rate", "Success rate", "Average Length", "Accuracy"]
                )
            )
            .all()
        )
        for m in metrics:
            print(f"ID: {m.id}, Name: {m.name}, Direction: {m.direction}")


if __name__ == "__main__":
    add_robotics_metrics()
