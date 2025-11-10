"""
Add scale values to existing metrics without scales.

This script queries metrics that don't have a scale yet and assigns appropriate
scales based on their names and conventions.
"""

import sys
from sqlalchemy import text
from backend.database.connection import db_manager


def main():
    """Add scales to metrics without them."""
    print("=" * 80)
    print("Add Scales to Existing Metrics")
    print("=" * 80)

    try:
        with db_manager.session_local() as session:
            # Get metrics without scales
            result = session.execute(
                text("""
                SELECT id, name, full_name, direction
                FROM metrics
                WHERE scale IS NULL
                ORDER BY name
            """)
            )

            metrics_without_scale = list(result)

            if not metrics_without_scale:
                print("\n✅ All metrics already have scales!")
                return 0

            print(f"\nFound {len(metrics_without_scale)} metrics without scales:\n")

            # Define scale mappings based on metric semantics
            scale_mappings = {
                # Accuracy/Performance metrics (0-100 percentages)
                "Accuracy": "0-100",
                "Test Accuracy": "0-100",
                "Val Accuracy": "0-100",
                # Error rates (typically 0-100 percentages)
                "Top-1 Error": "0-100",
                "Top-5 Error": "0-100",
                # Detection/Segmentation (0-100)
                "Mask mAP": "0-100",
                "Panoptic Quality": "0-100",
                "PQ": "0-100",
                # Video metrics
                "J&F": "0-100",  # Video segmentation metric
                # Retrieval/Ranking
                "Recall": "0-100",
                "R@1": "0-100",
                "R@5": "0-100",
                "R@10": "0-100",
                "mR": "0-100",  # mean Recall
                # Specific error metrics (unbounded)
                "PSNR": "unbounded",  # Peak Signal-to-Noise Ratio (dB)
                "SSIM": "0-1",  # Structural Similarity Index
                "LPIPS": "unbounded",  # Learned Perceptual Image Patch Similarity
                "IS": "unbounded",  # Inception Score
                "KID": "unbounded",  # Kernel Inception Distance
                # Time/efficiency metrics
                "Latency": "milliseconds",
                "Throughput": "unbounded",
                "FLOPs": "unbounded",
                "Params": "unbounded",
                # NLG/Captioning
                "CIDEr": "0-100",
                "SPICE": "0-100",
                # Question answering
                "EM": "0-100",  # Exact Match
                # Audio/Speech
                "SI-SNR": "unbounded",  # Scale-Invariant Signal-to-Noise Ratio (dB)
                "SDR": "unbounded",  # Signal-to-Distortion Ratio (dB)
                # Depth estimation thresholds
                "delta2": "0-1",
                "delta3": "0-1",
                # Other common metrics
                "PCK": "0-100",  # Percentage of Correct Keypoints
                "mCE": "0-100",  # mean Corruption Error
                # Defaults for common patterns
                # Most metrics ending in "Accuracy" or starting with "Top-" are percentages
            }

            updates_made = 0

            for metric_id, name, full_name, direction in metrics_without_scale:
                # Try to find a scale mapping
                scale = None

                # Direct lookup
                if name in scale_mappings:
                    scale = scale_mappings[name]
                # Pattern matching
                elif "Accuracy" in name or "accuracy" in name:
                    scale = "0-100"
                elif "Error" in name and "Rate" not in name:
                    scale = "unbounded"  # Most error metrics are unbounded
                elif "Rate" in name:
                    scale = "0-100"  # Error rates are typically percentages
                elif name.startswith("R@") or name.startswith("Recall@"):
                    scale = "0-100"  # Recall at K
                elif "Loss" in name:
                    scale = "unbounded"
                elif "Time" in name or "Latency" in name:
                    scale = "milliseconds"
                elif "FPS" in name or "throughput" in name.lower():
                    scale = "unbounded"
                elif "mAP" in name or name.endswith("AP"):
                    scale = "0-100"
                elif "IoU" in name or "IOU" in name:
                    scale = (
                        "0-1"
                        if "mean" not in name.lower() and "m" not in name
                        else "0-100"
                    )
                elif name.startswith("delta"):
                    scale = "0-1"  # Depth accuracy thresholds

                # If we found a scale, update it
                if scale:
                    session.execute(
                        text("""
                        UPDATE metrics
                        SET scale = :scale
                        WHERE id = :id
                    """),
                        {"scale": scale, "id": metric_id},
                    )
                    print(f"  ✓ {name:30s} → scale: {scale}")
                    updates_made += 1
                else:
                    # Leave without scale, can be added manually later
                    print(f"  ? {name:30s} → No automatic mapping (leaving NULL)")

            # Commit changes
            session.commit()

            print(f"\n{'=' * 80}")
            print(f"Updated {updates_made} metrics with scales")
            print(
                f"{len(metrics_without_scale) - updates_made} metrics still without scales (require manual review)"
            )
            print(f"{'=' * 80}")

            # Show final statistics
            result = session.execute(
                text("""
                SELECT
                    COUNT(*) as total,
                    COUNT(scale) as with_scale,
                    COUNT(*) - COUNT(scale) as without_scale
                FROM metrics
            """)
            )
            row = result.fetchone()
            print("\nFinal metrics summary:")
            print(f"  Total metrics: {row[0]}")
            print(f"  With scale: {row[1]}")
            print(f"  Without scale: {row[2]}")

        return 0

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
