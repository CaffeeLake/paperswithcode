"""Apply the verified cleanup and derived-protocol imports for VSR task 315."""

from backend.database.connection import get_database_session
from backend.models.database import Dataset, Evaluation
from backend.services.evaluation_service import EvaluationService

TASK_ID = 315
YOUHQ40 = 821
VIDEOLQ = 822
REDS4_BI = 914
VIMEO_BI = 915
VID4_BI = 917
UDM10_CONVENTIONAL = 918
SPMCS_CONVENTIONAL = 923
REALVSR_NATIVE = 926
REALVSR_DOVE = 1540
SPMCS_REALBASIC = 1541
UDM10_REALBASIC = 1542

DELETE_IDS = {
    # YouHQ40: RealESRGAN-degraded PS-SR and cropped/subset AdcVSR rows.
    *range(12654, 12661),
    *range(17026, 17034),
    # Native RealVSR: crop/subset AdcVSR/DLoRAL and original-scale STCDiT rows.
    *range(12449, 12452),
    *range(17034, 17037),
    *range(17072, 17075),
    # Conventional SPMCS/UDM10: cropped/subset AdcVSR rows.
    17024,
    17025,
    17018,
    17019,
    # Vid4 BI: Gaussian-BD, excluded-frame, or unresolved source-native protocols.
    12405,
    12406,
    12311,
    12312,
    12305,
    12306,
    12403,
    12404,
}

MOVE_TO_REALVSR_DOVE = {
    *range(12356, 12359),
    12461,
    12462,
    *range(12367, 12370),
    *range(17106, 17109),
    *range(17117, 17120),
    *range(17015, 17018),
}
MOVE_TO_SPMCS_REALBASIC = {
    12339,
    12340,
    12361,
    12362,
    12365,
    12366,
    17005,
    17006,
}

UDM10_IMPORTS = [
    (
        24150,
        "MGLD-VSR",
        "PSNR",
        "25.99",
        False,
        True,
        1_500_000_000,
        "https://huggingface.co/ianyeung/MGLD-VSR",
        "https://arxiv.org/abs/2312.00853",
    ),
    (
        24150,
        "MGLD-VSR",
        "SSIM",
        "0.7548",
        False,
        True,
        1_500_000_000,
        "https://huggingface.co/ianyeung/MGLD-VSR",
        "https://arxiv.org/abs/2312.00853",
    ),
    (
        34945,
        "RealViformer",
        "PSNR",
        "26.42",
        False,
        True,
        5_300_000,
        None,
        "https://arxiv.org/abs/2407.13987",
    ),
    (
        34945,
        "RealViformer",
        "SSIM",
        "0.7609",
        False,
        True,
        5_300_000,
        None,
        "https://arxiv.org/abs/2407.13987",
    ),
    (
        99363,
        "LSGQuant W4A4",
        "PSNR",
        "23.80",
        True,
        False,
        None,
        None,
        "https://arxiv.org/abs/2602.03182",
    ),
    (
        99363,
        "LSGQuant W4A4",
        "SSIM",
        "0.7130",
        True,
        False,
        None,
        None,
        "https://arxiv.org/abs/2602.03182",
    ),
    (
        64634,
        "STCDiT-tiny",
        "PSNR",
        "28.59",
        False,
        True,
        1_300_000_000,
        None,
        "https://arxiv.org/abs/2511.18786",
    ),
    (
        64634,
        "STCDiT-tiny",
        "SSIM",
        "0.8451",
        False,
        True,
        1_300_000_000,
        None,
        "https://arxiv.org/abs/2511.18786",
    ),
    (
        67194,
        "InfVSR",
        "PSNR",
        "24.86",
        True,
        False,
        1_300_000_000,
        None,
        "https://arxiv.org/abs/2510.00948",
    ),
    (
        67194,
        "InfVSR",
        "SSIM",
        "0.7274",
        True,
        False,
        1_300_000_000,
        None,
        "https://arxiv.org/abs/2510.00948",
    ),
    (
        67530,
        "OASIS",
        "PSNR",
        "25.63",
        True,
        False,
        1_420_000_000,
        None,
        "https://arxiv.org/abs/2509.23980",
    ),
    (
        67530,
        "OASIS",
        "SSIM",
        "0.7579",
        True,
        False,
        1_420_000_000,
        None,
        "https://arxiv.org/abs/2509.23980",
    ),
    (
        67514,
        "FastVSR (f8 encoder / f16 decoder)",
        "PSNR",
        "24.36",
        True,
        False,
        None,
        None,
        "https://arxiv.org/abs/2509.24142",
    ),
    (
        67514,
        "FastVSR (f8 encoder / f16 decoder)",
        "SSIM",
        "0.7184",
        True,
        False,
        None,
        None,
        "https://arxiv.org/abs/2509.24142",
    ),
    (
        71549,
        "DAM-VSR (ResShift ISR)",
        "PSNR",
        "27.011",
        True,
        True,
        None,
        "https://huggingface.co/Fucius/DAM-VSR",
        "https://arxiv.org/abs/2507.01012",
    ),
    (
        71549,
        "DAM-VSR (ResShift ISR)",
        "SSIM",
        "0.776",
        True,
        True,
        None,
        "https://huggingface.co/Fucius/DAM-VSR",
        "https://arxiv.org/abs/2507.01012",
    ),
    (
        74899,
        "DC-VSR (alternating SAP/TAP)",
        "PSNR",
        "28.71",
        False,
        True,
        None,
        "https://huggingface.co/Janghyeok/dc-vsr",
        "https://arxiv.org/abs/2502.03502",
    ),
    (
        74899,
        "DC-VSR (alternating SAP/TAP)",
        "SSIM",
        "0.8550",
        False,
        True,
        None,
        "https://huggingface.co/Janghyeok/dc-vsr",
        "https://arxiv.org/abs/2502.03502",
    ),
    (
        59034,
        "DUO-VSR",
        "PSNR",
        "24.94",
        True,
        False,
        1_300_000_000,
        None,
        "https://arxiv.org/abs/2603.22271",
    ),
    (
        59034,
        "DUO-VSR",
        "SSIM",
        "0.726",
        True,
        False,
        1_300_000_000,
        None,
        "https://arxiv.org/abs/2603.22271",
    ),
    (
        100526,
        "LiteVSR (Wan2.2-5B, 5-step full-rank adapter)",
        "PSNR",
        "23.01",
        True,
        False,
        5_600_000_000,
        None,
        "https://arxiv.org/abs/2606.09250",
    ),
    (
        42967,
        "DiffVSR",
        "PSNR",
        "23.181",
        True,
        True,
        None,
        "https://huggingface.co/huihui9998/DiffVSR",
        "https://arxiv.org/abs/2501.10110",
    ),
]


def require_rows(
    db, ids: set[int], expected_dataset: int | None = None
) -> list[Evaluation]:
    rows = db.query(Evaluation).filter(Evaluation.id.in_(ids)).all()
    found = {row.id for row in rows}
    if found != ids:
        raise RuntimeError(
            f"Expected evaluation ids {sorted(ids)}, found {sorted(found)}"
        )
    if expected_dataset is not None:
        wrong = [
            (row.id, row.dataset_id)
            for row in rows
            if row.dataset_id != expected_dataset
        ]
        if wrong:
            raise RuntimeError(f"Rows on unexpected datasets: {wrong}")
    return rows


def set_fields(db, ids: set[int], **values) -> None:
    rows = require_rows(db, ids)
    for row in rows:
        for key, value in values.items():
            setattr(row, key, value)


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        require_rows(db, DELETE_IDS)
        real_rows = require_rows(db, MOVE_TO_REALVSR_DOVE, REALVSR_NATIVE)
        spmcs_rows = require_rows(db, MOVE_TO_SPMCS_REALBASIC, SPMCS_CONVENTIONAL)

        for row in real_rows:
            row.dataset_id = REALVSR_DOVE
            row.methodology = (
                (row.methodology or "")
                + " Assigned to the derived DOVE-family RealVSR 4x protocol; not the native RealVSR source-paper contract."
            )
        for row in spmcs_rows:
            row.dataset_id = SPMCS_REALBASIC
            row.methodology = (
                (row.methodology or "")
                + " Assigned to the derived RealBasicVSR-style complex-degradation SPMCS protocol."
            )
        db.query(Evaluation).filter(Evaluation.id.in_(DELETE_IDS)).delete(
            synchronize_session=False
        )

        # Exact full-model metadata for DOVE and SparkVSR.
        dove_rows = (
            db.query(Evaluation)
            .filter(
                Evaluation.task_id == TASK_ID,
                Evaluation.paper_id == 49383,
                Evaluation.model_name == "DOVE",
            )
            .all()
        )
        for row in dove_rows:
            row.num_parameters = 5_787_190_000
            row.hf_model_url = "https://huggingface.co/ZhengChen1999/DOVE"
        spark_rows = (
            db.query(Evaluation)
            .filter(Evaluation.id.in_({12365, 12366, 12367, 12368, 12369}))
            .all()
        )
        for row in spark_rows:
            # The HF count covers transformer tensors only, not the full
            # VAE/text-encoder pipeline, and the paper gives no exact total.
            row.num_parameters = None

        set_fields(
            db,
            {12339, 12340},
            source_url="https://arxiv.org/abs/2312.06640",
            external_source_url="https://arxiv.org/abs/2312.06640",
        )
        set_fields(
            db,
            {12361, 12362},
            source_url="https://arxiv.org/abs/2505.16239",
            external_source_url="https://arxiv.org/abs/2505.16239",
        )
        set_fields(
            db,
            {12365, 12366},
            source_url="https://arxiv.org/abs/2603.16864",
            external_source_url="https://arxiv.org/abs/2603.16864",
        )

        # Source, openness, parameter, and protocol corrections from benchmark audits.
        set_fields(db, set(range(17151, 17162)), is_open=False)
        set_fields(db, {12271, 12272, 12273, 12274}, num_parameters=10_800_000)
        set_fields(db, {12283, 12284, 12285, 12286}, num_parameters=35_600_000)
        set_fields(
            db, {12333, 12334, 12335, 12336, 12337, 12338}, num_parameters=20_600_000
        )
        set_fields(db, {12335}, metrics={"PSNR": "37.61"})
        set_fields(db, {12336}, metrics={"SSIM": "0.9489"})
        set_fields(
            db,
            {12335, 12336},
            methodology="EDVR Table 2; Vimeo-90K-T BIx4; Y-channel PSNR/SSIM; seven-frame center prediction; zero spatial border crop.",
        )
        set_fields(
            db,
            {12301, 12302, 12299, 12300},
            source_url="https://paperswithcode.co/paper/2305.00163",
            external_source_url="https://arxiv.org/abs/2305.00163",
        )
        set_fields(
            db,
            {17086, 17087},
            is_open=False,
            methodology="Vimeo-90K-T BIx4; MATLAB bicubic generation compatible with BasicVSR; Y-channel center-frame evaluation; seven-frame clips mirrored to 14 frames; zero spatial border crop.",
        )
        set_fields(
            db,
            {17088, 17089},
            methodology="Vid4 BIx4; Y-channel PSNR/SSIM; zero spatial border crop; all frames included; per-sequence means averaged equally across Calendar, City, Foliage, and Walk.",
        )
        set_fields(db, {17075, 17076, 17077}, uses_additional_data=True)
        set_fields(
            db,
            {12255, 12256},
            methodology="UDM10 conventional BDx4 protocol (Gaussian blur sigma=1.6 followed by 4x downsampling); Y-channel PSNR/SSIM; 8-pixel HR border crop; all ten sequences.",
        )
        set_fields(
            db,
            {16977, 16978},
            methodology="UDM10 conventional BDx4 protocol (Gaussian blur sigma=1.6 followed by 4x downsampling); Y-channel PSNR/SSIM; 8-pixel HR border crop; all ten sequences.",
        )
        set_fields(db, {12275, 12276}, num_parameters=10_800_000)

        diff_scores = {
            17128: ("PSNR", "23.713"),
            17129: ("CLIP-IQA", "0.785"),
            17130: ("MUSIQ", "68.040"),
            17131: ("DOVER", "0.878"),
            17132: ("E_warp", "1.492"),
        }
        for row in require_rows(db, set(diff_scores)):
            metric, score = diff_scores[row.id]
            row.metrics = {metric: score}
            row.methodology = "DiffVSR paper standard YouHQ40 RealBasicVSR-degradation row; 4x VSR; source E_warp is the printed x10^-3 coefficient; DOVER normalized to the configured 0-1 scale."

        lsg_url = "https://github.com/zhengchen1999/LSGQuant/releases/download/supplement-v1/Supplementary_Material.pdf"
        set_fields(
            db,
            {17005, 17006, *range(17007, 17018)},
            source_url=lsg_url,
            external_source_url=lsg_url,
        )
        for ids in ({17014}, {17058}, {17105}, {17140}, {17195}):
            for row in require_rows(db, ids):
                row.methodology = (
                    row.methodology or ""
                ) + " E_warp is stored as the source's printed x10^-3 coefficient."

        descriptions = {
            REDS4_BI: "REDS4 BIx4 uses REDS clips 000, 011, 015, and 020 (not the distinct REDSval4 convention), bicubic 4x degradation, RGB PSNR/SSIM, zero border crop, and all-frame sequence averaging.",
            VIMEO_BI: "Vimeo-90K-T BIx4 uses the official septuplet test split with MATLAB bicubic 4x degradation, Y-channel PSNR/SSIM, zero border crop, and canonical center-frame evaluation.",
            VID4_BI: "Vid4 BIx4 uses Calendar, City, Foliage, and Walk with bicubic 4x degradation, Y-channel PSNR/SSIM, zero border crop, all frames, and equal averaging of the four per-sequence means.",
            UDM10_CONVENTIONAL: "UDM10 conventional BDx4 uses all ten PFNL test sequences, Gaussian blur sigma=1.6 followed by 4x downsampling, Y-channel PSNR/SSIM, and an 8-pixel HR border crop. Complex RealBasicVSR-style degradation belongs on the separate derived leaderboard.",
            SPMCS_CONVENTIONAL: "SPMCS conventional 4x is reserved for the source-family synthetic upscaling protocol (including the RRN Gaussian/Y-channel lineage). RealBasicVSR-style complex degradation belongs on the separate derived leaderboard.",
            REALVSR_NATIVE: "Native RealVSR follows the ICCV 2021 source-paper contract: 50 registered/cropped paired test sequences at equal pixel dimensions (the paper's x2 designation is the cameras' focal-length ratio), Y-channel PSNR/SSIM and RGB LPIPS. Later pixel-4x DOVE-family results belong on the separate derived leaderboard.",
        }
        for dataset_id, description in descriptions.items():
            dataset = db.get(Dataset, dataset_id)
            if dataset is None:
                raise RuntimeError(f"Missing dataset {dataset_id}")
            dataset.description = description

        # Add paper-native UDM10 complex-degradation cells that were held until
        # the derived leaderboard existed. Baseline/comparison-table rows remain excluded.
        for (
            paper_id,
            model,
            metric,
            score,
            extra,
            is_open,
            params,
            hf_url,
            source,
        ) in UDM10_IMPORTS:
            exists = (
                db.query(Evaluation)
                .filter(
                    Evaluation.paper_id == paper_id,
                    Evaluation.task_id == TASK_ID,
                    Evaluation.dataset_id == UDM10_REALBASIC,
                    Evaluation.model_name == model,
                    Evaluation.best_metric == metric,
                )
                .first()
            )
            if exists:
                raise RuntimeError(
                    f"Unexpected pre-existing UDM10 derived row {exists.id}"
                )
            db.add(
                Evaluation(
                    paper_id=paper_id,
                    task_id=TASK_ID,
                    dataset_id=UDM10_REALBASIC,
                    model_name=model,
                    methodology="Paper-native UDM10 4x result under the paper's training-matched RealBasicVSR-style complex degradation; full ten-sequence evaluation; comparator rows excluded.",
                    metrics={metric: score},
                    uses_additional_data=extra,
                    is_open=is_open,
                    best_metric=metric,
                    external_source_url=source,
                    source_url=source,
                    external=False,
                    num_parameters=params,
                    hf_model_url=hf_url,
                )
            )

        # STCDiT trains on UltraVideo plus LSDIR, beyond the baseline recipe.
        for row in db.query(Evaluation).filter(
            Evaluation.task_id == TASK_ID,
            Evaluation.dataset_id == UDM10_REALBASIC,
            Evaluation.paper_id == 64634,
        ):
            row.uses_additional_data = True

        db.commit()

        svc = EvaluationService(db)
        for dataset_id in [
            YOUHQ40,
            VIDEOLQ,
            REDS4_BI,
            VIMEO_BI,
            VID4_BI,
            UDM10_CONVENTIONAL,
            SPMCS_CONVENTIONAL,
            REALVSR_NATIVE,
            REALVSR_DOVE,
            SPMCS_REALBASIC,
            UDM10_REALBASIC,
        ]:
            svc.recalculate_ranks(TASK_ID, dataset_id)
        print(
            f"deleted={len(DELETE_IDS)} moved_realvsr={len(MOVE_TO_REALVSR_DOVE)} moved_spmcs={len(MOVE_TO_SPMCS_REALBASIC)} created_udm10={len(UDM10_IMPORTS)}"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
        session_gen.close()


if __name__ == "__main__":
    main()
