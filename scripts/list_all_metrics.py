from backend.database.connection import db_manager
from backend.models.database import Metric as DBMetric

session = db_manager.session_local()
try:
    metrics = session.query(DBMetric).order_by(DBMetric.name).all()

    print(f"Total metrics in database: {len(metrics)}\n")
    print("=" * 100)
    print(f"{'Metric Name':<40} {'Scale':<20} {'Direction':<20} {'Full Name':<40}")
    print("=" * 100)

    for m in metrics:
        name = m.name[:38] if len(m.name) > 38 else m.name
        scale = (m.scale or "None")[:18] if m.scale else "None"
        direction = m.direction[:18]
        full_name = (m.full_name or "")[:38] if m.full_name else ""
        print(f"{name:<40} {scale:<20} {direction:<20} {full_name:<40}")

    print("=" * 100)

    # Summary statistics
    metrics_with_scale = sum(1 for m in metrics if m.scale)
    metrics_without_scale = len(metrics) - metrics_with_scale

    print("\nSummary:")
    print(f"  Metrics with scale defined: {metrics_with_scale}")
    print(f"  Metrics without scale: {metrics_without_scale}")

    # Count by direction
    higher_is_better = sum(1 for m in metrics if m.direction == "higher_is_better")
    lower_is_better = sum(1 for m in metrics if m.direction == "lower_is_better")
    print(f"  Higher is better: {higher_is_better}")
    print(f"  Lower is better: {lower_is_better}")
finally:
    session.close()
