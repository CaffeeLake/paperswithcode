-- Backfill ObjectNet's benchmark source paper as a native local paper URL.
--
-- The previous dataset.paper_url pointed directly at a NeurIPS PDF. The
-- benchmark page's source fallback could misread that URL's /paper/2019/ path
-- segment as a local/arXiv paper id and render "arXiv:2019".

WITH source_paper AS (
    SELECT id
    FROM papers
    WHERE source = 'external'
      AND source_url = 'https://papers.nips.cc/paper/2019/hash/97af07a14cacba681feacf3012730892-Abstract.html'
),
inserted_paper AS (
    INSERT INTO papers (
        title,
        abstract,
        source,
        source_url,
        version,
        is_latest_version,
        date_published,
        proceeding,
        conference,
        conference_url_abs,
        conference_url_pdf,
        primary_category
    )
    SELECT
        'ObjectNet: A large-scale bias-controlled dataset for pushing the limits of object recognition models',
        'We collect a large real-world test set, ObjectNet, for object recognition with controls where object backgrounds, rotations, and imaging viewpoints are random. Most scientific experiments have controls, confounds which are removed from the data, to ensure that subjects cannot perform a task by exploiting trivial correlations in the data. Historically, large machine learning and computer vision datasets have lacked such controls. This has resulted in models that must be fine-tuned for new datasets and perform better on datasets than in real-world applications. When tested on ObjectNet, object detectors show a 40-45% drop in performance, with respect to their performance on other benchmarks, due to the controls for biases. Controls make ObjectNet robust to fine-tuning showing only small performance increases. We develop a highly automated platform that enables gathering datasets with controls by crowdsourcing image capturing and annotation. ObjectNet is the same size as the ImageNet test set (50,000 images), and by design does not come paired with a training set in order to encourage generalization. The dataset is both easier than ImageNet (objects are largely centered and unoccluded) and harder (due to the controls). Although we focus on object recognition here, data with controls can be gathered at scale using automated tools throughout machine learning to generate datasets that exercise models in new ways thus providing valuable feedback to researchers. This work opens up new avenues for research in generalizable, robust, and more human-like computer vision and in creating datasets where results are predictive of real-world performance.',
        'external',
        'https://papers.nips.cc/paper/2019/hash/97af07a14cacba681feacf3012730892-Abstract.html',
        'v1',
        true,
        DATE '2019-12-08',
        'NeurIPS 2019',
        'NeurIPS',
        'https://papers.nips.cc/paper/2019/hash/97af07a14cacba681feacf3012730892-Abstract.html',
        'https://papers.nips.cc/paper_files/paper/2019/file/97af07a14cacba681feacf3012730892-Paper.pdf',
        'cs.CV'
    WHERE NOT EXISTS (SELECT 1 FROM source_paper)
    RETURNING id
),
objectnet_paper AS (
    SELECT id FROM inserted_paper
    UNION ALL
    SELECT id FROM source_paper
),
objectnet_dataset AS (
    SELECT id
    FROM datasets
    WHERE id = 268
      AND name = 'ObjectNet'
)
UPDATE datasets d
SET introducing_paper_id = p.id,
    introducing_paper_title = 'ObjectNet: A large-scale bias-controlled dataset for pushing the limits of object recognition models',
    paper_url = 'https://paperswithcode.co/paper/' || p.id,
    introduced_year = 2019,
    updated_at = NOW()
FROM objectnet_dataset od
CROSS JOIN objectnet_paper p
WHERE d.id = od.id;

WITH objectnet_paper AS (
    SELECT introducing_paper_id AS paper_id
    FROM datasets
    WHERE id = 268
      AND name = 'ObjectNet'
      AND introducing_paper_id IS NOT NULL
),
objectnet_task AS (
    SELECT task_id
    FROM task_datasets
    WHERE dataset_id = 268
      AND task_id = 1
)
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.paper_id, t.task_id, 'manual'
FROM objectnet_paper p
CROSS JOIN objectnet_task t
ON CONFLICT (paper_id, task_id) DO UPDATE
SET source = 'manual';
