#!/usr/bin/env python3
"""Idempotently create the seven core Motion Sensing benchmark contracts.

The remaining canonical and Inertia-1 benchmarks have dedicated importers. This
module snapshots the early core rows that were originally assembled during the
field audit so the complete benchmark layer can be replayed and reviewed.
"""

from datetime import date
import json

from sqlalchemy import text

from backend.database.connection import get_database_session


TASK_SLUG = "motion-sensing"

SPECS = (
    {
        "name": "UCI HAR",
        "full_name": "Human Activity Recognition Using Smartphones",
        "slug": "uci-har",
        "description": "UCI HAR contains smartphone accelerometer and gyroscope recordings from 30 volunteers performing six activities of daily living. Its canonical benchmark protocol uses the official subject-disjoint split: 21 volunteers for training and 9 held-out volunteers for testing, with performance reported as classification accuracy.",
        "short_description": "Smartphone inertial-sensor recordings from 30 subjects across six daily activities, evaluated on the official subject-held-out train/test split.",
        "url": "https://archive.ics.uci.edu/dataset/240/human+activity+recognition+using+smartphones",
        "homepage": "https://archive.ics.uci.edu/dataset/240/human+activity+recognition+using+smartphones",
        "source_title": "A Public Domain Dataset for Human Activity Recognition Using Smartphones",
        "source_arxiv": None,
        "license_name": "Public domain",
        "license_url": None,
        "introduced_date": date(2013, 4, 24),
        "introduced_year": 2013,
        "modalities": ["Time series"],
        "variants": ["Official subject-held-out train/test split"],
        "variant_type": None,
        "split_name": "Official subject-held-out train/test split (21 train subjects / 9 test subjects)",
        "warning": None,
        "pwc_url": "https://paperswithcode.com/dataset/har",
        "metric_id": 18,
    },
    {
        "name": "Opportunity Gesture Recognition",
        "full_name": "Opportunity Challenge — Task B2 Gesture Recognition",
        "slug": "opportunity-gesture-recognition",
        "description": "The Opportunity Challenge Task B2 continuous gesture-recognition benchmark. Models classify 17 labels (16 right-arm gesture classes plus Null) from the full on-body sensor set. The held-out test set is ADL4 and ADL5 from subjects 2 and 3. Ranking uses the prevalence-weighted F1 over the 16 gesture/activity classes, excluding the Null class; locomotion (Task A), binary spotting (Task B1), and the noisy subject-4 protocol (Task C) are separate and must not be mixed into this leaderboard.",
        "short_description": "Continuous recognition of 16 right-arm gestures plus Null from wearable on-body sensors under the canonical Opportunity Challenge Task B2 protocol.",
        "url": "https://archive.ics.uci.edu/dataset/226/opportunity+activity+recognition",
        "homepage": "https://archive.ics.uci.edu/dataset/226/opportunity+activity+recognition",
        "source_title": "The Opportunity challenge: A benchmark database for on-body sensor-based activity recognition",
        "source_arxiv": None,
        "license_name": None,
        "license_url": None,
        "introduced_date": date(2013, 11, 1),
        "introduced_year": 2013,
        "modalities": [
            "wearable inertial sensors",
            "accelerometer",
            "gyroscope",
            "magnetometer",
        ],
        "variants": None,
        "variant_type": "split",
        "split_name": "Task B2 test: Subjects 2–3, ADL4–ADL5",
        "warning": "Protocol-specific leaderboard: Task B2 only (subjects 2 and 3, ADL4/ADL5, full on-body sensors); Weighted F1 excludes the Null class. Do not mix Task A locomotion, Task B1 spotting, Task C rotational-noise, or alternative train/test splits.",
        "pwc_url": None,
        "metric_id": 417,
    },
    {
        "name": "MHEALTH",
        "full_name": "MHEALTH (Mobile Health) Dataset",
        "slug": "mhealth",
        "description": "MHEALTH is a multimodal wearable-sensing dataset containing body-motion and vital-sign recordings from 10 volunteers performing 12 physical activities. This leaderboard uses subject-independent leave-one-subject-out (LOSO) evaluation and reports macro-averaged F1 on a 0–1 scale.",
        "short_description": "Multimodal body-motion and vital-sign recordings from 10 subjects performing 12 activities, evaluated with subject-independent LOSO Macro F1.",
        "url": "https://archive.ics.uci.edu/dataset/319/mhealth+dataset",
        "homepage": "https://archive.ics.uci.edu/dataset/319/mhealth+dataset",
        "source_title": "mHealthDroid: A Novel Framework for Agile Development of Mobile Health Applications",
        "source_arxiv": None,
        "license_name": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "introduced_date": date(2014, 12, 2),
        "introduced_year": 2014,
        "modalities": ["Time series"],
        "variants": ["Subject-independent LOSO"],
        "variant_type": None,
        "split_name": "Subject-independent leave-one-subject-out (LOSO) cross-validation",
        "warning": None,
        "pwc_url": None,
        "metric_id": 415,
    },
    {
        "name": "CAPTURE-24 Activity Classification",
        "full_name": "CAPTURE-24 — Free-Living Activities of Daily Living Classification",
        "slug": "capture-24-activity-classification",
        "description": "Official CAPTURE-24 free-living activity-of-daily-living classification benchmark using dominant-wrist tri-axial accelerometry. The data are segmented into fixed non-overlapping 10-second windows and mapped to 10 classes. The participant-disjoint protocol derives models on P001–P100 and evaluates once on held-out P101–P151. Report Macro F1 on the fixed 51-participant test set on a 0–1 scale.",
        "short_description": "Ten-class free-living human activity recognition from wrist-worn accelerometry, evaluated on 51 held-out participants.",
        "url": "https://doi.org/10.5287/bodleian:NGx0JOMP5",
        "homepage": "https://github.com/activityMonitoring/capture24",
        "source_title": "CAPTURE-24: A large dataset of wrist-worn activity tracker data collected in the wild for human activity recognition",
        "source_arxiv": "2402.19229",
        "license_name": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "introduced_date": date(2024, 2, 29),
        "introduced_year": 2024,
        "modalities": ["wrist-worn accelerometry", "wearable inertial sensors"],
        "variants": None,
        "variant_type": "split",
        "split_name": "Held-out participants P101–P151",
        "warning": "Protocol-specific leaderboard: use the official 10-class activities-of-daily-living labels and fixed held-out-participant test set P101–P151. Do not mix the separate 4-class physical-activity-intensity task, participant-overlapping splits, or results on other datasets.",
        "pwc_url": None,
        "metric_id": 415,
    },
    {
        "name": "MotionSense",
        "full_name": "MotionSense Dataset for Human Activity and Attribute Recognition",
        "slug": "motionsense",
        "description": "MotionSense contains 50 Hz accelerometer and gyroscope-derived time series collected with an iPhone 6s carried in the front pocket of 24 participants performing six activities across 15 trials. This leaderboard reports activity-classification accuracy under subject-independent evaluation, with participants kept disjoint between training and test sets.",
        "short_description": "iPhone accelerometer and gyroscope recordings from 24 participants performing six activities, evaluated with participant-disjoint activity classification.",
        "url": "https://github.com/mmalekzadeh/motion-sense",
        "homepage": "https://github.com/mmalekzadeh/motion-sense",
        "source_title": "Protecting Sensory Data against Sensitive Inferences",
        "source_arxiv": "1802.07802",
        "license_name": "MIT",
        "license_url": "https://opensource.org/license/mit/",
        "introduced_date": date(2018, 2, 21),
        "introduced_year": 2018,
        "modalities": ["Time series"],
        "variants": ["MotionSense"],
        "variant_type": None,
        "split_name": "Subject-independent activity classification (participant-disjoint train/test split)",
        "warning": "Only participant-disjoint evaluations are comparable. Randomly splitting overlapping or adjacent windows from the same participant across train and test sets causes identity and temporal leakage and must not be ranked on this leaderboard.",
        "pwc_url": "https://paperswithcode.com/dataset/motionsense",
        "metric_id": 18,
    },
    {
        "name": "WEAR Outdoor Sports Activity Recognition",
        "full_name": "WEAR — Four-IMU Outdoor Sports Activity Classification (LOSO)",
        "slug": "wear-outdoor-sports-activity-recognition",
        "description": "Official WEAR inertial activity-classification benchmark using synchronized 50 Hz tri-axial acceleration from four fixed wrist/ankle placements. Evaluation follows leave-one-subject-out cross-validation over the original 18 participants and three random seeds. Predictions cover 18 workout activities plus Null/background and are scored with record/window-level Macro F1 on a 0–1 scale.",
        "short_description": "Held-out-subject classification of 18 outdoor workout activities plus background from four wrist/ankle accelerometers.",
        "url": "https://mariusbock.github.io/wear/",
        "homepage": "https://mariusbock.github.io/wear/",
        "source_title": "WEAR: An Outdoor Sports Dataset for Wearable and Egocentric Activity Recognition",
        "source_arxiv": "2304.05088",
        "license_name": None,
        "license_url": None,
        "introduced_date": date(2023, 4, 11),
        "introduced_year": 2023,
        "modalities": ["wearable inertial sensors", "accelerometer"],
        "variants": None,
        "variant_type": "split",
        "split_name": "Leave-one-subject-out (18 participants)",
        "warning": "Protocol-specific leaderboard: four fixed-placement 3-axis accelerometers, 50 Hz; LOSO over the original 18 participants; 18 workout labels plus Null/background; record/window-level Macro F1. Do not mix sensor ablations, video/fused results, temporal-localization mAP, later challenge splits, or coarser label mappings.",
        "pwc_url": None,
        "metric_id": 415,
    },
    {
        "name": "RecoFit",
        "full_name": "RecoFit Exercise Recognition from Wearable Sensors",
        "slug": "recofit",
        "description": "RecoFit contains arm-worn accelerometer and gyroscope recordings from participants performing repetitive gym exercises. The recognition leaderboard uses participant-held-out leave-one-participant-out evaluation and reports macro-averaged F1 on a 0–1 scale.",
        "short_description": "Arm-worn inertial-sensor recordings of repetitive exercises, evaluated with participant-held-out exercise recognition.",
        "url": "https://github.com/microsoft/Exercise-Recognition-from-Wearable-Sensors",
        "homepage": "https://github.com/microsoft/Exercise-Recognition-from-Wearable-Sensors",
        "source_title": "RecoFit: Using a Wearable Sensor to Find, Recognize, and Count Repetitive Exercises",
        "source_arxiv": None,
        "license_name": "CDLA-Permissive-2.0",
        "license_url": "https://cdla.dev/permissive-2-0/",
        "introduced_date": date(2014, 4, 26),
        "introduced_year": 2014,
        "modalities": ["Time series"],
        "variants": ["Exercise recognition"],
        "variant_type": None,
        "split_name": "Participant-held-out exercise recognition (leave-one-participant-out)",
        "warning": "This leaderboard is only for exercise recognition and uses Macro F1 on a 0–1 scale. Repetition-counting errors, segmentation metrics, recognition accuracy, and participant-overlapping splits are separate protocols.",
        "pwc_url": None,
        "metric_id": 415,
    },
)


def resolve_source_paper_id(db, spec: dict) -> int:
    if spec["source_arxiv"]:
        paper_id = db.execute(
            text(
                """
                SELECT id FROM papers
                WHERE arxiv_id = :arxiv_id AND is_latest_version
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"arxiv_id": spec["source_arxiv"]},
        ).scalar_one_or_none()
    else:
        paper_id = db.execute(
            text(
                """
                SELECT id FROM papers
                WHERE lower(title) = lower(:title)
                ORDER BY is_latest_version DESC, id DESC LIMIT 1
                """
            ),
            {"title": spec["source_title"]},
        ).scalar_one_or_none()
    if paper_id is None:
        raise RuntimeError(f"Missing introducing paper: {spec['source_title']}")
    return int(paper_id)


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    try:
        task_id = db.execute(
            text("SELECT id FROM tasks WHERE slug = :slug"), {"slug": TASK_SLUG}
        ).scalar_one()
        for spec in SPECS:
            source_paper_id = resolve_source_paper_id(db, spec)
            params = {
                **spec,
                "source_paper_id": source_paper_id,
                "paper_url": f"https://paperswithcode.co/paper/{spec['source_arxiv'] or source_paper_id}",
                "modalities_json": json.dumps(spec["modalities"]),
                "variants_json": json.dumps(spec["variants"]),
            }
            dataset_id = db.execute(
                text(
                    """
                    INSERT INTO datasets (
                        name, full_name, slug, description, short_description,
                        url, homepage, introducing_paper_id,
                        introducing_paper_title, license_name, license_url,
                        introduced_date, introduced_year, modalities, variants,
                        variant_type, split_name, warning, pwc_url, paper_url
                    ) VALUES (
                        :name, :full_name, :slug, :description, :short_description,
                        :url, :homepage, :source_paper_id,
                        :source_title, :license_name, :license_url,
                        :introduced_date, :introduced_year,
                        CAST(:modalities_json AS jsonb), CAST(:variants_json AS jsonb),
                        :variant_type, :split_name, :warning, :pwc_url, :paper_url
                    )
                    ON CONFLICT (slug) DO UPDATE SET
                        name = EXCLUDED.name,
                        full_name = EXCLUDED.full_name,
                        description = EXCLUDED.description,
                        short_description = EXCLUDED.short_description,
                        url = EXCLUDED.url,
                        homepage = EXCLUDED.homepage,
                        introducing_paper_id = EXCLUDED.introducing_paper_id,
                        introducing_paper_title = EXCLUDED.introducing_paper_title,
                        license_name = EXCLUDED.license_name,
                        license_url = EXCLUDED.license_url,
                        introduced_date = EXCLUDED.introduced_date,
                        introduced_year = EXCLUDED.introduced_year,
                        modalities = EXCLUDED.modalities,
                        variants = EXCLUDED.variants,
                        variant_type = EXCLUDED.variant_type,
                        split_name = EXCLUDED.split_name,
                        warning = EXCLUDED.warning,
                        pwc_url = EXCLUDED.pwc_url,
                        paper_url = EXCLUDED.paper_url,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING id
                    """
                ),
                params,
            ).scalar_one()
            db.execute(
                text(
                    """
                    INSERT INTO task_datasets (task_id, dataset_id, featured_rank, supports_harness)
                    VALUES (:task_id, :dataset_id, NULL, false)
                    ON CONFLICT (task_id, dataset_id) DO UPDATE SET
                        featured_rank = NULL,
                        supports_harness = false,
                        updated_at = CURRENT_TIMESTAMP
                    """
                ),
                {"task_id": task_id, "dataset_id": dataset_id},
            )
            db.execute(
                text(
                    """
                    INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                    VALUES (:task_id, :dataset_id, :metric_id)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "task_id": task_id,
                    "dataset_id": dataset_id,
                    "metric_id": spec["metric_id"],
                },
            )
            db.execute(
                text(
                    """
                    INSERT INTO paper_tasks (paper_id, task_id, source)
                    VALUES (:paper_id, :task_id, 'manual')
                    ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                    """
                ),
                {"paper_id": source_paper_id, "task_id": task_id},
            )
            print(
                f"{spec['slug']} dataset_id={dataset_id} metric_id={spec['metric_id']}"
            )
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
