"""Apply verification fixes from full ISR benchmark audit (round 2)."""

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService

DELETE_IDS = [
    # DIV2K-Val: ASASR uses 1024×256 protocol
    11656,
    11657,
    11658,
    11659,
    11660,
    11661,
    11662,
    # RealSR: full-image / NR-only protocol mismatches
    12205,
    12206,
    12207,
    12208,
    12209,
    12210,  # FluxSR-s1
    12056,
    12057,  # ResShift
    12113,
    12114,  # SinSR
    # DRealSR: quantized + NSARM 1024→512 protocol
    12197,
    12198,
    12199,
    12200,  # Q-DiT4SR W4A6
    11941,
    11942,
    11943,
    11944,
    11945,
    11946,  # NSARM
    # Classical ×4: RGB / lightweight / legacy RGB
    11692,  # Set5 DRCT-L (RGB)
    11824,  # BSD100 UCAN-L (lightweight track)
    11695,  # Urban100 DRCT-L (RGB)
    11760,  # Urban100 SelfExSR (RGB)
    11697,  # Manga109 DRCT-L (RGB)
]

SCORE_FIXES = {
    # Set5: self-ensemble → single-pass Y-channel
    11713: (
        "HAT FIR†",
        "33.26",
        "SwinFIR Table 4 ×4 Set5, HAT FIR† single-pass; Y-channel PSNR",
    ),
    11699: (
        "CPAT",
        "33.19",
        "CPAT Table 5 ×4 Set5, CPAT (Ours) single-pass; Y-channel PSNR",
    ),
    11726: (
        "RGT",
        "33.12",
        "RGT Table 2 ×4 Set5, RGT (ours) single-pass; Y-channel PSNR",
    ),
    11736: (
        "DAT",
        "33.08",
        "DAT Table 2 ×4 Set5, DAT (ours) single-pass; Y-channel PSNR",
    ),
    # BSD100
    11740: ("DAT", "28.00", "DAT Table 2 ×4 B100, single-pass; Y-channel PSNR"),
    11730: ("RGT", "28.00", "RGT Table 2 ×4 B100, single-pass; Y-channel PSNR"),
    11703: ("CPAT", "28.04", "CPAT Table 5 ×4 B100, single-pass; Y-channel PSNR"),
    11715: (
        "HAT FIR†",
        "28.07",
        "SwinFIR Table 5 ×4 B100, HAT FIR† without +FE; Y-channel PSNR",
    ),
    # Urban100
    11716: (
        "HAT FIR†",
        "28.40",
        "SwinFIR Table 5 ×4 Urban100, HAT FIR† without +FE; Y-channel PSNR",
    ),
    11705: (
        "CPAT",
        "28.22",
        "CPAT Table 5 ×4 Urban100, CPAT single-pass; Y-channel PSNR",
    ),
    11732: ("RGT", "27.98", "RGT Table 2 ×4 Urban100, RGT single-pass; Y-channel PSNR"),
    11742: ("DAT", "27.87", "DAT Table 2 ×4 Urban100, DAT single-pass; Y-channel PSNR"),
}

FLUXSR_DIV2K_OPEN = list(range(12211, 12217))
ALIGNVAR_DREALSR_CLOSED = list(range(11816, 11822))
ASASR_REALSR_METHODOLOGY = list(range(11663, 11670))

ASASR_REALSR_METH = (
    "Table 1 RealSR, arXiv 2605.23264; 128×128 LR → 512×512 HR center-crop "
    "(StableSR protocol); PSNR/SSIM on Y channel; pyiqa NR metrics"
)


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    svc = EvaluationService(db)
    stats = {"deleted": 0, "updated": 0}

    try:
        for eid in DELETE_IDS:
            svc.delete_evaluation(eid)
            stats["deleted"] += 1

        for eid, (model_name, score, methodology) in SCORE_FIXES.items():
            svc.update_evaluation(
                eid,
                model_name=model_name,
                metrics={"PSNR": score},
                best_metric="PSNR",
                methodology=methodology,
            )
            stats["updated"] += 1

        for eid in FLUXSR_DIV2K_OPEN:
            svc.update_evaluation(eid, is_open=True)
            stats["updated"] += 1

        for eid in ALIGNVAR_DREALSR_CLOSED:
            svc.update_evaluation(eid, is_open=False)
            stats["updated"] += 1

        for eid in ASASR_REALSR_METHODOLOGY:
            svc.update_evaluation(eid, methodology=ASASR_REALSR_METH)
            stats["updated"] += 1

        db.commit()
        print("Round-2 fix complete:", stats)

        with db.connection() as conn:
            for slug in [
                "div2k-val-real-esrgan-x4",
                "realsr",
                "drealsr",
                "set5-4x-upscaling",
                "set14-4x-upscaling",
                "bsd100-4x-upscaling",
                "urban100-4x-upscaling",
                "manga109-4x-upscaling",
            ]:
                n = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM evaluations e "
                        "JOIN datasets d ON d.id = e.dataset_id "
                        "WHERE d.slug = :slug AND e.task_id = 314"
                    ),
                    {"slug": slug},
                ).scalar()
                print(f"  {slug}: {n} rows")

    except Exception:
        db.rollback()
        raise
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
