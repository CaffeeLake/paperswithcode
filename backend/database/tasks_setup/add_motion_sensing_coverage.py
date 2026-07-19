#!/usr/bin/env python3
"""Index and manually tag the curated Motion Sensing top-100 paper ledger."""

import argparse
import asyncio

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.services.paper_service import PaperService
from backend.utils.keyword_matching import (
    create_keyword_patterns,
    find_matching_items_simple,
)


NOT_RESULTS = {
    "2001.07416": "field survey/review",
    "2111.00418": "field survey/review",
    "2407.07196": "field survey/review",
    "2101.01665": "field survey/review",
    "2508.12213": "field survey/review",
    "2402.19229": "benchmark/dataset paper",
    "2510.09539": "benchmark/dataset paper",
    "2512.10807": "benchmark/dataset paper",
}

# Exact-phrase matches that are outside the wearable human-motion scope.
EXCLUDED_AUTO_ARXIV_IDS = {
    "2309.07550",  # robot-arm trajectory generation using a wearable IMU
    "2403.13841",  # affect forecasting from personal tracking diaries
    "2410.14879",  # visualization system for personal tracking data
    "2605.07552",  # visual-inertial 3D pose estimation, outside activity sensing
    "2602.20651",  # generic functional-data method; wearable sensing is only an example
    "2601.06937",  # synthetic mental-health function-calling dataset
    "2603.07559",  # Kinect RGB micro-gesture recognition, not wearable sensing
}

LIVE_EXTRA_DECISIONS = {
    "2506.16840": (
        "defer-incompatible-protocol",
        "FedFitTech uses within-client temporal WEAR splits rather than participant LOSO",
    ),
    "2605.22715": (
        "imported",
        "AnyMo paper-native official-split UCI HAR Accuracy row",
    ),
    "2603.10961": (
        "defer-incompatible-protocol",
        "Bio-PM uses custom wrist-only 10-second transfer protocols",
    ),
    "2510.25785": (
        "defer-no-db-match",
        "HiMAE evaluates PPG clinical and sleep tasks without live boards",
    ),
    "2512.19729": (
        "defer-incompatible-protocol",
        "FlowFM uses custom wrist-only 30 Hz 10-second protocols with unspecified splits",
    ),
    "2412.15947": (
        "defer-no-db-match",
        "private ANNE One sleep-staging cohort has no live board",
    ),
    "2510.09930": (
        "defer-incompatible-protocol",
        "prompted chronological timestep segmentation is not canonical participant-heldout HAR",
    ),
}

LIVE_SOURCE_NOT_RESULTS = {
    "external:104205": "HAR70+ benchmark/source paper",
    "external:104206": "OdayFoG benchmark/source paper",
    "external:104200": "HARTH benchmark/dataset paper",
    "external:104212": "MM-Fit benchmark/dataset paper",
    "1802.07802": "MotionSense benchmark/dataset and privacy paper",
    "external:104195": "MHEALTH source/framework paper",
    "external:104203": "RecoFit benchmark/dataset paper",
    "2304.05088": "WEAR benchmark/dataset paper",
    "2206.14568": "ADARP dataset paper",
    "external:104207": "FoGTurning benchmark/dataset paper",
}

EXCLUDED_AUTO_PAPER_IDS = {
    96715,  # ankle-exoskeleton controller, not activity/motion representation learning
}

FINAL_DECISIONS = {
    "1708.08989": ("imported", "UCI HAR paper-native Accuracy row"),
    "2206.02909": (
        "defer-incompatible-protocol",
        "verifier found an 8-activity wrist-only 10-second PAMAP2 setup",
    ),
    "2006.14435": (
        "defer-incompatible-protocol",
        "reported WISDM/PAMAP2/Opportunity splits and metrics do not match the canonical boards",
    ),
    "2312.05409": (
        "defer-no-db-match",
        "private PPG/ECG health probes do not match inertial activity-recognition boards",
    ),
    "2202.12938": (
        "defer-incompatible-protocol",
        "grouped five-fold and metric/label setups differ from the canonical LOSO and Accuracy boards",
    ),
    "2102.01875": (
        "defer-incompatible-protocol",
        "Opportunity result is four-class locomotion, not the 17-label Task B2 gesture board",
    ),
    "2003.09018": (
        "defer-incompatible-protocol",
        "verifier found a 9-subject accelerometer/gyroscope PAMAP2 setup",
    ),
    "2410.13638": (
        "defer-no-db-match",
        "private multimodal Fitbit/Pixel Watch activity dataset has no comparable public board",
    ),
    "1806.05226": (
        "defer-not-paper-native",
        "protocol paper reports reimplementations of external methods rather than an introduced model",
    ),
    "2505.19369": (
        "defer-incompatible-protocol",
        "newer 51-subject WISDM release and random window split do not match WISDM v1.1 cross-subject",
    ),
    "2501.08471": (
        "defer-not-paper-native",
        "comparative benchmark contains established generic models and incompatible record-level splits",
    ),
    "2202.00758": (
        "defer-incompatible-protocol",
        "ColloSSL uses group-heldout PAMAP2 and four-label Opportunity locomotion protocols",
    ),
    "2209.09092": ("imported", "TASKED paper-native LOSO rows on PAMAP2 and MHEALTH"),
    "2506.05321": (
        "defer-no-db-match",
        "private 20-class day-scale multimodal activity dataset has no comparable public board",
    ),
    "1808.08615": (
        "defer-no-db-match",
        "custom nine-user textile-stretch/ankle-accelerometer dataset has no configured board",
    ),
    "2402.01049": (
        "defer-incompatible-protocol",
        "verifier found the IMUGPT PAMAP2 evaluation uses 9 subjects",
    ),
    "2412.09758": (
        "defer-incompatible-protocol",
        "NormWear reports UCI HAR AUROC under a custom split rather than official-split Accuracy",
    ),
    "2503.17978": (
        "defer-incompatible-protocol",
        "verifier found LOSO only within a downstream subset after disjoint SSL pretraining",
    ),
    "2508.11186": (
        "imported",
        "KAN paper-native participant-disjoint MotionSense Accuracy row",
    ),
    "2507.13482": (
        "defer-no-db-match",
        "MMEA few-shot and private four-patient PD datasets have no comparable live board",
    ),
    "2109.02054": (
        "defer-missing-metric",
        "UCI HAR and MotionSense report mean F1 while canonical boards require Accuracy",
    ),
    "2209.11750": (
        "defer-incompatible-protocol",
        "HART/MobileHART metrics or splits differ on UCI HAR, MotionSense, HHAR, and RealWorld",
    ),
    "2403.20183": (
        "defer-incompatible-protocol",
        "HARMamba uses generic sample-level 70/10/20 splits instead of subject-independent contracts",
    ),
    "2203.07910": (
        "defer-incompatible-protocol",
        "HAR-ResGCNN uses sample-level five-fold splits and a reduced PAMAP2 label set",
    ),
    "2406.01646": (
        "defer-not-comparable",
        "iKAN reports only cross-dataset continual-learning aggregates and incompatible per-task setups",
    ),
    "2210.14395": (
        "defer-no-db-match",
        "IMU2CLIP evaluates custom Ego4D and Aria head-mounted activity tasks without live boards",
    ),
    "2310.02011": (
        "imported",
        "FusionActNet paper-native UCI HAR and MotionSense Accuracy rows",
    ),
    "2001.05517": (
        "defer-incompatible-protocol",
        "personalized MHEALTH Accuracy and later smartwatch WISDM do not match canonical boards",
    ),
    "2503.13542": (
        "defer-incompatible-protocol",
        "HAR-DoReMi uses a four-class multi-source domain-generalization protocol",
    ),
    "2411.18822": (
        "defer-incompatible-protocol",
        "verifier found an 8-activity wrist-only 10-second PAMAP2 setup",
    ),
    "2507.00050": (
        "defer-incompatible-protocol",
        "SEZ-HARN uses zero-shot class-held-out folds and per-class Accuracy, not subject LOSO Macro F1",
    ),
    "2402.09434": (
        "defer-incompatible-protocol",
        "MHNN does not establish the exact subject splits and changes several sensor/label setups",
    ),
    "2508.01701": (
        "defer-no-db-match",
        "MHARFedLLM evaluates only the multimodal MEx physiotherapy dataset",
    ),
    "2603.19564": (
        "not-a-results-paper",
        "position/survey paper without introduced experiments",
    ),
    "2507.00061": (
        "defer-incompatible-protocol",
        "Smooth-Distill uses random window splits, altered labels, and later WISDM generation",
    ),
    "2604.18058": (
        "defer-incompatible-protocol",
        "Sonata uses sparse-label two-subject and cross-dataset PAMAP2 protocols",
    ),
    "2602.19004": (
        "defer-no-db-match",
        "MoBind evaluates multimodal mRi, TotalCapture, and EgoHumans tasks without live boards",
    ),
    "2506.12561": (
        "defer-no-db-match",
        "tDCSFoG/DeFOG Kaggle competition protocol does not match live FoG boards",
    ),
    "2605.09173": (
        "defer-no-db-match",
        "WavesFM evaluates Fitbit clinical phenotypes rather than activity-recognition contracts",
    ),
    "2505.10312": (
        "defer-no-db-match",
        "SOS evaluates only OpenPack industrial activity recognition, which has no live board",
    ),
    "2604.21369": (
        "defer-incompatible-protocol",
        "verifier found the late-fusion result averages over 9 PAMAP2 subjects",
    ),
    "2512.09775": (
        "defer-missing-metric",
        "reports uncertainty-agreement rather than HAR performance under altered RealWorld/HHAR setups",
    ),
    "2505.04907": (
        "defer-incompatible-protocol",
        "VaCDA uses reduced-label cross-position/domain-adaptation Micro F1 setups",
    ),
    "2605.12019": (
        "defer-missing-metric",
        "HARLLM reports weighted F1 or random-fraction HHAR splits rather than canonical metrics",
    ),
    "2605.18837": (
        "defer-no-db-match",
        "VCR evaluates PPG-DaLiA incomplete-modality activity recognition without a live board",
    ),
    "2604.23281": (
        "defer-incompatible-protocol",
        "CLMM uses a fixed 7/2-subject one-percent-label PAMAP2 protocol",
    ),
    "2602.08755": (
        "defer-no-db-match",
        "AliAd evaluates CMDFall, DailySport, RealDisp, and UP-Fall without live boards",
    ),
    "2603.11526": (
        "defer-missing-metric",
        "CFD-HAR reports unidentified generic F1 without a MotionSense split or protocol",
    ),
    "2601.22265": (
        "defer-incompatible-protocol",
        "verifier found the reported test set is a custom 15-participant accelerometer dataset",
    ),
    "2509.21673": (
        "defer-incompatible-protocol",
        "SlotFM uses five-fold two-second Macro F1 protocols rather than canonical or Inertia boards",
    ),
    "2507.01068": (
        "defer-incompatible-protocol",
        "uses only two FoGTurning subject files with ordinary train/test and nested CV",
    ),
    "2509.24176": (
        "defer-no-db-match",
        "FM-FoG evaluates a new VCU FoG-IMU cohort; public FoG datasets are pretraining-only",
    ),
    "2506.09108": (
        "defer-no-db-match",
        "SensorLM uses a private Fitbit/Pixel Watch cohort with custom downstream tasks",
    ),
    "2507.03250": (
        "defer-no-db-match",
        "SICL evaluates UTD-MHAD, MMAct, and DARai without live boards",
    ),
    "2602.00809": (
        "defer-no-db-match",
        "custom four-class Duck Catch & Fit exergame dataset has no live board",
    ),
    "2507.00191": (
        "defer-no-db-match",
        "Wearable Behavior Model evaluates AHMS health and sleep tasks rather than HAR labels",
    ),
    "2412.11276": (
        "defer-no-db-match",
        "private AHMS retrieval, physiology, demographics, and survey tasks are not HAR benchmarks",
    ),
    "2503.07259": (
        "defer-no-db-match",
        "COMODO evaluates custom Ego4D, EgoExo4D, and MMEA subsets without live boards",
    ),
    "2010.16052": (
        "defer-no-db-match",
        "HHAR-Net evaluates ExtraSensory, not the HHAR dataset",
    ),
    "2411.11764": (
        "defer-no-db-match",
        "FOGSense evaluates tDCSFoG, explicitly distinct from live FoG boards",
    ),
    "2406.01316": (
        "defer-incompatible-protocol",
        "Multi3Net uses wrist-only MM-Fit LOSO Macro F1 instead of full multimodal fixed-split Accuracy",
    ),
    "2401.05437": (
        "defer-missing-metric",
        "UCI HAR scores are unlabeled figure bars under an unconfirmed random subject split",
    ),
    "2406.03857": ("imported", "MuJo paper-native zero-shot MotionSense Accuracy row"),
    "2411.14070": (
        "defer-no-db-match",
        "federated HAR results are exclusively on ExtraSensory",
    ),
    "2407.12287": (
        "defer-no-db-match",
        "CDFL evaluates image-based Stanford40, PPMI, and VOC2012 rather than wearable sensing",
    ),
    "2411.15240": (
        "defer-no-db-match",
        "PAT evaluates NHANES clinical outcomes rather than activity recognition",
    ),
    "2210.01459": (
        "defer-incompatible-protocol",
        "verifier found Optional activities and no explicit 8-subject protocol cohort",
    ),
    "2306.13735": (
        "defer-incompatible-protocol",
        "multi-dataset LODO harmonizes sensors, labels, splits, and metrics away from canonical boards",
    ),
    "1808.02870": (
        "defer-no-db-match",
        "private wrist-based OFF/ON/DYS Parkinson cohort is not a live FoG board",
    ),
    "2402.08451": (
        "defer-no-db-match",
        "Moonwalk gait-authentication datasets have no live activity-recognition board",
    ),
    "2409.16730": (
        "defer-incompatible-protocol",
        "custom 20 Hz six-second UCI/MHEALTH preprocessing has unspecified subject splits",
    ),
    "2410.10624": ("imported", "SensorLLM official-split UCI HAR Accuracy row"),
    "2406.11914": (
        "defer-incompatible-protocol",
        "KAN variants use half-subject holdouts and Macro F1 rather than canonical splits/metrics",
    ),
    "2406.14498": (
        "defer-missing-metric",
        "LLaSA reports F1 without canonical held-participant splits and trains on target sensor data",
    ),
    "2410.19818": ("imported", "UniMTS released official-split UCI HAR Accuracy row"),
    "2410.10167": (
        "defer-no-db-match",
        "X-Fi evaluates MM-Fi and XRF55; MM-Fi is distinct from wearable MM-Fit",
    ),
    "2303.04636": (
        "defer-incompatible-protocol",
        "Centaur alters PAMAP2, Opportunity, and HHAR sensors/tasks/splits/metrics",
    ),
    "2407.06628": (
        "defer-incompatible-protocol",
        "EVI-MAE uses fixed-split WEAR Accuracy, not canonical LOSO Macro F1 or Inertia AUROC/AUPRC",
    ),
    "2307.02906": (
        "defer-no-db-match",
        "custom nursing-activity pose/IMU dataset has no live board",
    ),
    "2409.18481": (
        "defer-no-db-match",
        "DHC-HGL evaluates WASH and ExtraSensory without live boards",
    ),
    "2305.10222": (
        "defer-incompatible-protocol",
        "rWISDM five-class micro-F1 matches neither v1.1 nor the 18-class Inertia variant",
    ),
    "2304.14912": (
        "defer-incompatible-protocol",
        "random-test Accuracy and Capture24 kappa do not match LOSO/fixed-test leaderboard metrics",
    ),
    "2301.10161": (
        "defer-incompatible-protocol",
        "explicit MotionSense score has same-subject leakage; participant-disjoint plots lack exact values",
    ),
    "2304.09530": (
        "defer-incompatible-protocol",
        "SelfAct changes HHAR/MotionSense labels, sensors, groups, and metrics",
    ),
    "2305.12824": (
        "defer-no-db-match",
        "FieldHAR evaluates a custom multimodal kitchen-activity dataset",
    ),
    "2309.01262": (
        "defer-no-db-match",
        "multimodal UTD-MHAD and MMAct have no live boards; MMAct is not MM-Fit",
    ),
    "2311.04236": (
        "defer-incompatible-protocol",
        "fixed-subject PAMAP2 and reduced-label HARTH curves are not canonical and lack exact scores",
    ),
    "2205.12781": (
        "defer-incompatible-protocol",
        "UniMiB-SHAR Accuracy lacks any stated subject split or cross-validation scheme",
    ),
    "1802.09745": (
        "defer-no-db-match",
        "ReHAR is video action recognition on NCAA Basketball and UCF Sports",
    ),
    "2607.06617": (
        "imported",
        "26 best introduced AUROC/AUPRC rows across all 13 exact Inertia-1 variants",
    ),
    "2306.05285": (
        "defer-incompatible-protocol",
        "SF-DM uses single-sensor custom splits and reduced labels on MM-Fit/PAMAP2/Opportunity",
    ),
    "2112.13755": (
        "defer-no-db-match",
        "HomeKit influenza detection is not motion or activity classification",
    ),
}

# Ranked from the combined Semantic Scholar citation/recent searches, Hugging Face
# paper search, legacy PwC leads, local task signals, GitHub evidence, and
# comparison-table expansion. Order is the curation rank, not the live trend rank.
TOP_100_ARXIV_IDS = """
2001.07416 2111.00418 1708.08989 2206.02909 2006.14435 2312.05409
2202.12938 2407.07196 2402.19229 2003.09018 2102.01875 2410.13638
1806.05226 2505.19369 2501.08471 2209.09092 2202.00758 2607.06617
2506.05321 1808.08615 2402.01049 2101.01665 2412.09758 2503.17978
2508.11186 2403.20183 2507.13482 2109.02054 2209.11750 2203.07910
2406.01646 2210.14395 2001.05517 2310.02011 2503.13542 2411.18822
2402.09434 2507.00050 2508.01701 2603.19564 2507.00061 2604.18058
2602.19004 2506.12561 2605.09173 2605.18837 2505.10312 2604.21369
2512.09775 2505.04907 2605.12019 2604.23281 2602.08755 2601.22265
2510.09539 2603.11526 2509.21673 2507.01068 2509.24176 2508.12213
2506.09108 2512.10807 2602.00809 2507.03250 2507.00191 2503.07259
2412.11276 2010.16052 2406.01316 2411.11764 2401.05437 2406.03857
2411.14070 2210.01459 2407.12287 2411.15240 2306.13735 1808.02870
2402.08451 2410.10624 2409.16730 2410.19818 2406.11914 2406.14498
2407.06628 2410.10167 2303.04636 2307.02906 2409.18481 2305.10222
2301.10161 2304.14912 2304.09530 2311.04236 2305.12824 2309.01262
2205.12781 1802.09745 2306.05285 2112.13755
""".split()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index-missing", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    assert len(TOP_100_ARXIV_IDS) == 100
    assert len(set(TOP_100_ARXIV_IDS)) == 100

    session_gen = get_database_session()
    db = next(session_gen)
    service = PaperService(db)
    try:
        task_id = db.execute(
            text("SELECT id FROM tasks WHERE slug = 'motion-sensing'")
        ).scalar_one()
        task_keywords = db.execute(
            text("SELECT keywords FROM tasks WHERE id = :task_id"),
            {"task_id": task_id},
        ).scalar_one()

        # Earlier exploratory keyword sets were broader than the final task
        # definition. The corpus linker is additive, so remove only stale
        # automatic links; manual curation and benchmark-source tags are never
        # touched.
        case_sensitive, case_insensitive = create_keyword_patterns(
            [{"id": task_id, "keywords": task_keywords}]
        )
        auto_rows = db.execute(
            text(
                """
                SELECT p.id, p.arxiv_id, p.title, p.abstract
                FROM paper_tasks pt
                JOIN papers p ON p.id = pt.paper_id
                WHERE pt.task_id = :task_id AND pt.source = 'auto'
                """
            ),
            {"task_id": task_id},
        ).mappings()
        stale_auto_ids = [
            row["id"]
            for row in auto_rows
            if row["arxiv_id"] in EXCLUDED_AUTO_ARXIV_IDS
            or row["id"] in EXCLUDED_AUTO_PAPER_IDS
            or task_id
            not in find_matching_items_simple(
                f"{row['title']} {row['abstract'] or ''}",
                case_sensitive,
                case_insensitive,
            )
        ]
        print(f"stale_auto_links={len(stale_auto_ids)}")
        if args.apply and stale_auto_ids:
            db.execute(
                text(
                    """
                    DELETE FROM paper_tasks
                    WHERE task_id = :task_id
                      AND source = 'auto'
                      AND paper_id = ANY(:paper_ids)
                    """
                ),
                {"task_id": task_id, "paper_ids": stale_auto_ids},
            )
            db.commit()
        existing = {
            row.arxiv_id: row.id
            for row in db.execute(
                text(
                    """
                    SELECT DISTINCT ON (arxiv_id) arxiv_id, id
                    FROM papers
                    WHERE arxiv_id = ANY(:ids)
                    ORDER BY arxiv_id, is_latest_version DESC, id DESC
                    """
                ),
                {"ids": TOP_100_ARXIV_IDS},
            ).mappings()
        }

        missing = [aid for aid in TOP_100_ARXIV_IDS if aid not in existing]
        print(f"ledger=100 existing={len(existing)} missing={len(missing)}")
        if args.index_missing:
            for index, arxiv_id in enumerate(missing, 1):
                result = asyncio.run(service.refresh_arxiv_paper(arxiv_id))
                existing[arxiv_id] = int(result.paper.id)
                print(
                    f"indexed {index}/{len(missing)} {arxiv_id} paper_id={result.paper.id}"
                )

        if args.apply:
            unresolved = [aid for aid in TOP_100_ARXIV_IDS if aid not in existing]
            if unresolved:
                raise RuntimeError(f"Cannot tag unresolved papers: {unresolved}")
            for arxiv_id in TOP_100_ARXIV_IDS:
                db.execute(
                    text(
                        """
                        INSERT INTO paper_tasks (paper_id, task_id, source)
                        VALUES (:paper_id, :task_id, 'manual')
                        ON CONFLICT (paper_id, task_id)
                        DO UPDATE SET source = 'manual'
                        """
                    ),
                    {"paper_id": existing[arxiv_id], "task_id": task_id},
                )
            db.commit()

        rows = db.execute(
            text(
                """
                SELECT p.arxiv_id, p.title, p.date_published, p.citation_count,
                       p.trending_score, p.hf_models, p.hf_datasets, p.hf_spaces,
                       count(e.id) AS eval_count
                FROM papers p
                LEFT JOIN evaluations e ON e.paper_id = p.id
                WHERE p.arxiv_id = ANY(:ids) AND p.is_latest_version
                GROUP BY p.id
                ORDER BY array_position(:ids, p.arxiv_id)
                """
            ),
            {"ids": TOP_100_ARXIV_IDS},
        ).mappings()
        for rank, row in enumerate(rows, 1):
            arxiv_id = row["arxiv_id"]
            if arxiv_id in FINAL_DECISIONS:
                decision, reason = FINAL_DECISIONS[arxiv_id]
            elif arxiv_id in NOT_RESULTS:
                decision = "not-a-results-paper"
                reason = NOT_RESULTS[arxiv_id]
            else:
                decision = "defer-missing-benchmark"
                reason = "pending paper-native table inspection after benchmark wiring"
            print(
                f"{rank:03d}\t{arxiv_id}\t{decision}\t{row['eval_count']}\t"
                f"{reason}\t{row['title']}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
