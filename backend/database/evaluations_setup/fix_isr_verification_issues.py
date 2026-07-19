"""Apply verification fixes for ISR leaderboard imports (Tier 1 + Tier 2)."""

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.evaluation_service import EvaluationService

TASK_ID = 314
DIV2K = 885
REALSR = 884
DREALSR = 825

PAPER_IDS = {
    "TinySR": 69248,
    "AddSR": 29825,
    "DiffBIR": 19894,
    "VOSR": 58556,
    "AlignVAR": 102608,
    "DTPSR": 84792,
}

ADDSR_FIXES = {
    DIV2K: {
        12058: ("PSNR", "21.83"),
        12059: ("SSIM", "0.5651"),
        12060: ("LPIPS", "0.2812"),
        12061: ("MANIQA", "0.6430"),
        12062: ("MUSIQ", "71.43"),
        12063: ("CLIPIQA+", "0.7794"),
    },
    REALSR: {
        12064: ("PSNR", "22.73"),
        12065: ("SSIM", "0.6336"),
        12066: ("MANIQA", "0.6597"),
        12067: ("MUSIQ", "72.25"),
        12068: ("CLIPIQA+", "0.7215"),
    },
    DREALSR: {
        12069: ("PSNR", "26.09"),
        12070: ("SSIM", "0.7036"),
        12071: ("MANIQA", "0.6034"),
        12072: ("MUSIQ", "68.16"),
        12073: ("CLIPIQA+", "0.7381"),
    },
}

DIFFBIR_S1 = {
    DIV2K: {
        "PSNR": "21.9154",
        "SSIM": "0.4986",
        "LPIPS": "0.4263",
        "MUSIQ": "61.1476",
        "MANIQA": "0.2466",
        "CLIPIQA+": "0.6347",
    },
    DREALSR: {
        "PSNR": "25.6238",
        "SSIM": "0.6544",
        "LPIPS": "0.2350",
        "MUSIQ": "69.8821",
        "MANIQA": "0.3530",
        "CLIPIQA+": "0.6440",
    },
    REALSR: {
        "PSNR": "24.7531",
        "SSIM": "0.6615",
        "LPIPS": "0.2565",
        "MUSIQ": "69.5167",
        "MANIQA": "0.3504",
        "CLIPIQA+": "0.6478",
    },
}

VOSR_REALSR = {
    "PSNR": "25.2284",
    "SSIM": "0.7175",
    "LPIPS": "0.2732",
    "DISTS": "0.2054",
    "MUSIQ": "70.5813",
    "MANIQA": "0.6443",
    "CLIPIQA+": "0.6392",
}

DELETE_IDS = [
    # DTPSR wrong metric
    11805,
    # VOSR cherry-picked variants
    11763,
    11764,
    11765,
    11766,
    11767,
    11768,
    # DiffBIR — all rows replaced with unified s=1
    12032,
    12033,
    12034,
    12035,
    12036,
    12037,
    12038,
    12039,
    12040,
    12041,
    12042,
    12043,
    12044,
    12045,
    12046,
    12047,
    12048,
    12049,
    # DIV2K protocol mismatches
    11873,
    11874,
    11875,
    11876,
    11877,  # HYPIR
    11878,
    11879,
    11880,
    11881,
    11882,
    11883,  # LinearSR DIV2K
    11935,
    11936,
    11937,
    11938,
    11939,
    11940,  # NSARM DIV2K
    12050,
    12051,
    12052,
    12053,
    12054,
    12055,  # SUPIR DIV2K
    # RealSR protocol mismatches
    11884,
    11885,
    11886,
    11887,
    11888,
    11889,  # LinearSR RealSR
    11947,
    11948,
    11949,
    11950,
    11951,
    11952,  # NSARM RealSR
    11806,
    11807,  # DACESR RealSR
    12106,
    12107,
    12108,
    12109,
    12110,
    12111,
    12112,  # DreamClear RealSR
    12099,
    12100,
    12101,
    12102,
    12103,
    12104,
    12105,  # DreamClear DRealSR
]

TINYSR_IDS = list(range(11917, 11935))
ALIGNVAR_REALSR_IDS = list(range(11810, 11816))


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    svc = EvaluationService(db)
    stats = {"deleted": 0, "updated": 0, "created": 0}

    try:
        for eid in DELETE_IDS:
            svc.delete_evaluation(eid)
            stats["deleted"] += 1

        for eid in TINYSR_IDS:
            svc.update_evaluation(eid, is_open=True)
            stats["updated"] += 1

        for eid in ALIGNVAR_REALSR_IDS:
            svc.update_evaluation(eid, is_open=False)
            stats["updated"] += 1

        addsr_methodology = {
            DIV2K: "Table 1 Single SR (×4), DIV2K-val synthetic, AddSR-4; arXiv 2404.01717",
            REALSR: "Table 3 AddSR-4, RealSR; arXiv 2404.01717",
            DREALSR: "Table 3 AddSR-4, DRealSR; arXiv 2404.01717",
        }
        for dataset_id, fixes in ADDSR_FIXES.items():
            for eid, (metric, score) in fixes.items():
                svc.update_evaluation(
                    eid,
                    metrics={metric: score},
                    best_metric=metric,
                    methodology=addsr_methodology[dataset_id],
                )
                stats["updated"] += 1

        diffbir_methodology = (
            "DiffBIR Table 2/10, guidance scale s=1 (unified variant); "
            "arXiv 2308.15070; CLIP-IQA stored as CLIPIQA+"
        )
        for dataset_id, metrics in DIFFBIR_S1.items():
            for metric, score in metrics.items():
                svc.create_evaluation(
                    paper_id=PAPER_IDS["DiffBIR"],
                    task_id=TASK_ID,
                    dataset_id=dataset_id,
                    metrics={metric: score},
                    model_name="DiffBIR",
                    best_metric=metric,
                    methodology=diffbir_methodology,
                    is_open=True,
                    num_parameters=1_716_700_000,
                )
                stats["created"] += 1

        vosr_methodology = (
            "Table 1 RealSR, VOSR-1.4B-os (one-step); arXiv 2604.03225; "
            "128×128 LR → 512×512 HR center-crop protocol"
        )
        for metric, score in VOSR_REALSR.items():
            svc.create_evaluation(
                paper_id=PAPER_IDS["VOSR"],
                task_id=TASK_ID,
                dataset_id=REALSR,
                metrics={metric: score},
                model_name="VOSR-1.4B-os",
                best_metric=metric,
                methodology=vosr_methodology,
                is_open=True,
            )
            stats["created"] += 1

        db.commit()
        print("Fix complete:", stats)

        with db.connection() as conn:
            for arxiv in [
                "2508.17434",
                "2404.01717",
                "2308.15070",
                "2604.03225",
                "2603.00589",
                "2603.07430",
            ]:
                row = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM evaluations e "
                        "JOIN papers p ON p.id=e.paper_id "
                        "WHERE p.arxiv_id=:a AND p.is_latest_version"
                    ),
                    {"a": arxiv},
                ).scalar()
                print(f"  {arxiv}: {row} eval rows remaining")

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
