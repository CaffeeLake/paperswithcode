-- Build the medical question-answering taxonomy and restore/add its major
-- text and visual benchmarks. Evaluation rows are curated separately through
-- EvaluationService so each result retains paper-level provenance.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM tasks WHERE slug = 'question-answering') THEN
        RAISE EXCEPTION 'Question Answering task precondition failed';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM tasks WHERE slug = 'medical-imaging') THEN
        RAISE EXCEPTION 'Medical Imaging task precondition failed';
    END IF;
END
$$;

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
SELECT
    'Medical Question Answering',
    'medical-question-answering',
    'Medical question answering evaluates systems that answer biomedical, clinical, examination, and consumer-health questions from text. It is a specialized form of [Question Answering](/tasks/question-answering) spanning multiple-choice medical knowledge, evidence-grounded biomedical answers, clinical reading comprehension, and explanation generation.',
    'medical question answering, medical QA, MedQA, biomedical question answering, clinical question answering, healthcare question answering, medical exam question answering, medical reasoning, biomedical QA',
    p.area_id,
    p.level + 1,
    p.id,
    NULL,
    '[What Disease does this Patient Have? A Large-scale Open Domain Question Answering Dataset from Medical Exams](/paper/2009.13081)',
    NULL
FROM tasks p
WHERE p.slug = 'question-answering'
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

UPDATE tasks AS child
SET parent_id = parent.id,
    level = parent.level + 1,
    area_id = parent.area_id,
    description = 'Medical visual question answering (Med-VQA) requires a system to answer natural-language questions about clinical or biomedical images. It combines [Medical Imaging](/tasks/medical-imaging) with [Question Answering](/tasks/question-answering) and is evaluated on both closed-ended diagnostic questions and open-ended answer generation.',
    updated_at = CURRENT_TIMESTAMP
FROM tasks AS parent
WHERE child.slug = 'medical-visual-question-answering'
  AND parent.slug = 'medical-imaging';

INSERT INTO metrics (name, full_name, direction, scale, description)
VALUES
    ('Answer F1', 'Answer Span F1', 'higher_is_better', '0-100', 'Token-overlap F1 between predicted and reference answer spans.'),
    ('BERTScore', 'BERTScore', 'higher_is_better', '0-100', 'Semantic similarity between generated and reference answers using contextual embeddings.')
ON CONFLICT (name) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    direction = EXCLUDED.direction,
    scale = EXCLUDED.scale,
    description = EXCLUDED.description,
    updated_at = CURRENT_TIMESTAMP;

WITH benchmark_data (
    name, full_name, slug, description, short_description, homepage, hf_url,
    introduced_date, modalities, languages, variants, arxiv_id, source_url
) AS (
    VALUES
    ('PMC-VQA', 'PMC Visual Question Answering', 'pmc-vqa',
     'PMC-VQA is a large-scale medical visual question-answering benchmark containing 227,000 question-answer pairs over 149,000 images from PMC Open Access articles. It includes a manually verified test set and supports classification-style and generative evaluation.',
     'A large-scale medical VQA benchmark with 227K QA pairs over 149K images.',
     'https://github.com/xiaoman-zhang/PMC-VQA', 'https://huggingface.co/datasets/xmcmic/PMC-VQA',
     '2023-05-17', '["images","text","medical"]', '["English"]', '["official split","manually verified test set"]', '2305.10415', NULL),
    ('BioASQ', 'Biomedical Semantic Indexing and Question Answering', 'bioasq',
     'BioASQ is a recurring biomedical question-answering challenge built from expert-authored questions, relevant biomedical articles and snippets, exact answers, and ideal paragraph answers. This leaderboard covers the question-answering component rather than the separate semantic-indexing or BEIR retrieval tasks.',
     'Expert biomedical questions with evidence, exact answers, and ideal answers.',
     'https://www.bioasq.org/', NULL,
     '2015-04-30', '["text","medical"]', '["English"]', '["question answering task"]', NULL, 'https://doi.org/10.1186/s12859-015-0564-6'),
    ('OmniMedVQA', 'OmniMedVQA', 'omnimedvqa',
     'OmniMedVQA is a comprehensive medical visual question-answering benchmark collected from 73 medical datasets, spanning 12 imaging modalities and more than 20 anatomical regions using images from real medical scenarios.',
     'A broad medical LVLM benchmark spanning 73 datasets and 12 modalities.',
     'https://github.com/OpenGVLab/Multi-Modality-Arena', NULL,
     '2024-02-14', '["images","text","medical"]', '["English"]', '["official evaluation set"]', '2402.09181', NULL),
    ('GMAI-MMBench', 'General Medical AI Multimodal Benchmark', 'gmai-mmbench',
     'GMAI-MMBench is a large multimodal medical benchmark constructed from 284 datasets across 38 medical image modalities, 18 clinical tasks, 18 departments, and four perceptual granularities, all represented in visual question-answering format.',
     'A general medical multimodal benchmark covering 284 datasets and 38 modalities.',
     'https://uni-medical.github.io/GMAI-MMBench.github.io/', 'https://huggingface.co/datasets/OpenGVLab/GMAI-MMBench',
     '2024-08-06', '["images","text","medical"]', '["English"]', '["official test set"]', '2408.03361', NULL),
    ('VQA-Med 2019', 'ImageCLEF 2019 VQA-Med', 'vqa-med-2019',
     'VQA-Med 2019 is the second ImageCLEF shared task for answering natural-language questions about medical images. It defines official train, validation, and test sets and evaluates normalized answers using strict accuracy and BLEU.',
     'The 2019 ImageCLEF medical visual question-answering shared task.',
     'https://www.imageclef.org/2019/medical/vqa', NULL,
     '2019-09-09', '["images","text","medical"]', '["English"]', '["2019 challenge split"]', NULL, 'https://www.imageclef.org/2019/medical/vqa'),
    ('VQA-Med 2020', 'ImageCLEF 2020 VQA-Med', 'vqa-med-2020',
     'VQA-Med 2020 is the third ImageCLEF medical visual question-answering shared task. Its VQA split contains 4,000 training, 500 validation, and 500 test radiology image-question pairs evaluated with strict accuracy and BLEU.',
     'The 2020 ImageCLEF VQA benchmark on radiology images.',
     'https://www.imageclef.org/2020/medical/vqa', NULL,
     '2020-09-22', '["images","text","medical","radiology"]', '["English"]', '["2020 challenge split"]', NULL, 'https://www.imageclef.org/2020/medical/vqa'),
    ('VQA-Med 2021', 'ImageCLEF 2021 VQA-Med', 'vqa-med-2021',
     'VQA-Med 2021 is the fourth ImageCLEF medical visual question-answering shared task. It focuses the VQA test set on abnormality questions over radiology images and evaluates normalized answers with strict accuracy and BLEU.',
     'The 2021 ImageCLEF VQA benchmark focused on radiology abnormalities.',
     'https://www.imageclef.org/2021/medical/vqa', NULL,
     '2021-09-21', '["images","text","medical","radiology"]', '["English"]', '["2021 challenge split"]', NULL, 'https://www.imageclef.org/2021/medical/vqa'),
    ('HEAD-QA', 'Healthcare Exam Question Answering', 'headqa',
     'HEAD-QA is a multiple-choice healthcare question-answering benchmark built from examinations for specialized positions in the Spanish healthcare system. It supports Spanish monolingual and English cross-lingual evaluation of complex medical reasoning.',
     'Medical-exam multiple-choice QA in Spanish with an English translation.',
     'http://aghie.github.io/head-qa/', NULL,
     '2019-06-11', '["text","medical"]', '["Spanish","English"]', '["Spanish","English translation"]', '1906.04701', NULL),
    ('CliCR', 'Clinical Case Reports Machine Reading Comprehension', 'clicr',
     'CliCR is a clinical machine-reading-comprehension benchmark containing roughly 100,000 cloze-style questions generated from clinical case reports. Many examples require medical domain knowledge, entity tracking, and spatiotemporal reasoning.',
     'About 100K cloze questions derived from clinical case reports.',
     'https://github.com/clips/clicr', NULL,
     '2018-03-26', '["text","medical"]', '["English"]', '["official split"]', '1803.09720', NULL),
    ('RadQA', 'Radiology Report Question Answering', 'radqa',
     'RadQA contains 3,074 physician-authored questions over radiology reports and 6,148 annotated answer-evidence pairs. Answers are spans in report Findings and Impressions, and the benchmark includes organically unanswerable questions.',
     'Physician-authored extractive QA over radiology reports.',
     'https://github.com/krobertslab/datasets/tree/master/radqa', NULL,
     '2022-06-01', '["text","medical","radiology"]', '["English"]', '["official split"]', NULL, 'https://doi.org/10.63317/2rkacs78gax6'),
    ('CMB', 'Comprehensive Medical Benchmark in Chinese', 'cmb',
     'CMB is a localized Chinese medical benchmark covering medical examinations and clinical diagnostic questions, including traditional Chinese medicine. It evaluates medical knowledge and clinical response quality in the native Chinese linguistic and cultural setting.',
     'A comprehensive native-Chinese benchmark for medical knowledge and clinical QA.',
     'https://github.com/FreedomIntelligence/CMB', 'https://huggingface.co/datasets/FreedomIntelligence/CMB',
     '2023-08-17', '["text","medical"]', '["Chinese"]', '["CMB-Exam","CMB-Clin"]', '2308.08833', NULL),
    ('CMExam', 'Chinese Medical Licensing Examination', 'cmexam',
     'CMExam contains more than 60,000 multiple-choice questions from the Chinese National Medical Licensing Examination, with solution explanations and professional annotations for disease groups, departments, disciplines, competency areas, and difficulty.',
     'Over 60K Chinese medical licensing-exam questions with explanations and annotations.',
     'https://github.com/williamliujl/CMExam', NULL,
     '2023-06-05', '["text","medical"]', '["Chinese"]', '["multiple choice","explanation generation"]', '2306.03030', NULL),
    ('MedExQA', 'Medical Question Answering with Multiple Explanations', 'medexqa',
     'MedExQA contains 965 medical multiple-choice questions across five underrepresented specialties, with multiple explanations for each question-answer pair. It evaluates both answer accuracy and the quality of generated medical explanations.',
     'Medical QA across five specialties with multiple reference explanations.',
     'https://github.com/knowlab/MedExQA', 'https://huggingface.co/datasets/bluesky333/MedExQA',
     '2024-06-10', '["text","medical"]', '["English"]', '["MCQ accuracy","explanation generation"]', '2406.06331', NULL),
    ('MedExpQA', 'Multilingual Medical Question Answering with Explanations', 'medexpqa',
     'MedExpQA is a multilingual medical-exam benchmark with physician-written gold explanations. It evaluates answer selection and explanation-grounded reasoning in English, French, Italian, and Spanish.',
     'A four-language medical-exam QA benchmark with physician-written explanations.',
     'https://huggingface.co/datasets/HiTZ/MedExpQA', 'https://huggingface.co/datasets/HiTZ/MedExpQA',
     '2024-04-08', '["text","medical"]', '["English","French","Italian","Spanish"]', '["gold explanations","retrieval-augmented settings"]', '2404.05590', NULL),
    ('AfriMed-QA', 'Pan-African Medical Question Answering', 'afrimed-qa',
     'AfriMed-QA is a Pan-African, multi-specialty medical QA benchmark with 15,000 open- and closed-ended questions sourced from more than 60 medical schools across 16 countries and 32 medical specialties.',
     'A 15K-question Pan-African medical QA benchmark spanning 16 countries.',
     'https://huggingface.co/datasets/intronhealth/afrimedqa_v2', 'https://huggingface.co/datasets/intronhealth/afrimedqa_v2',
     '2024-11-23', '["text","medical"]', '["English"]', '["expert MCQ","short answer","consumer questions"]', '2411.15640', NULL)
), resolved AS (
    SELECT b.*, p.id AS paper_id, p.title AS paper_title, p.arxiv_id AS resolved_arxiv_id
    FROM benchmark_data b
    JOIN papers p ON p.is_latest_version
      AND ((b.arxiv_id IS NOT NULL AND p.arxiv_id = b.arxiv_id)
        OR (b.source_url IS NOT NULL AND p.source = 'external' AND p.source_url = b.source_url))
)
INSERT INTO datasets (
    name, full_name, slug, description, short_description, url, hf_url, homepage,
    introducing_paper_id, introducing_paper_title, paper_url,
    introduced_date, introduced_year, modalities, languages, variants, pwc_url
)
SELECT
    name, full_name, slug, description, short_description, homepage, hf_url, homepage,
    paper_id, paper_title,
    CASE WHEN resolved_arxiv_id IS NOT NULL
         THEN 'https://paperswithcode.co/paper/' || resolved_arxiv_id
         ELSE 'https://paperswithcode.co/paper/' || paper_id::text END,
    introduced_date::date, EXTRACT(YEAR FROM introduced_date::date)::integer,
    modalities::jsonb, languages::jsonb, variants::jsonb,
    'https://paperswithcode.com/dataset/' || slug
FROM resolved
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    url = EXCLUDED.url,
    hf_url = EXCLUDED.hf_url,
    homepage = EXCLUDED.homepage,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    paper_url = EXCLUDED.paper_url,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    modalities = EXCLUDED.modalities,
    languages = EXCLUDED.languages,
    variants = EXCLUDED.variants,
    pwc_url = EXCLUDED.pwc_url,
    updated_at = CURRENT_TIMESTAMP;

-- Link each benchmark to its precise medical-QA child task. Broad parent task
-- pages inherit these leaderboards through task hierarchy traversal.
WITH links(dataset_slug, task_slug) AS (
    VALUES
    ('pathvqa', 'medical-visual-question-answering'),
    ('slake', 'medical-visual-question-answering'),
    ('vqa-rad', 'medical-visual-question-answering'),
    ('medxpertqa-mm', 'medical-visual-question-answering'),
    ('pmc-vqa', 'medical-visual-question-answering'),
    ('omnimedvqa', 'medical-visual-question-answering'),
    ('gmai-mmbench', 'medical-visual-question-answering'),
    ('vqa-med-2019', 'medical-visual-question-answering'),
    ('vqa-med-2020', 'medical-visual-question-answering'),
    ('vqa-med-2021', 'medical-visual-question-answering'),
    ('medqa', 'medical-question-answering'),
    ('pubmedqa', 'medical-question-answering'),
    ('medmcqa', 'medical-question-answering'),
    ('medxpertqa-text', 'medical-question-answering'),
    ('bioasq', 'medical-question-answering'),
    ('headqa', 'medical-question-answering'),
    ('clicr', 'medical-question-answering'),
    ('radqa', 'medical-question-answering'),
    ('cmb', 'medical-question-answering'),
    ('cmexam', 'medical-question-answering'),
    ('medexqa', 'medical-question-answering'),
    ('medexpqa', 'medical-question-answering'),
    ('afrimed-qa', 'medical-question-answering')
)
INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM links l
JOIN tasks t ON t.slug = l.task_slug
JOIN datasets d ON d.slug = l.dataset_slug
ON CONFLICT (task_id, dataset_id) DO UPDATE SET
    supports_harness = FALSE,
    updated_at = CURRENT_TIMESTAMP;

WITH metric_links(dataset_slug, task_slug, metric_name) AS (
    VALUES
    ('pmc-vqa', 'medical-visual-question-answering', 'Accuracy'),
    ('pmc-vqa', 'medical-visual-question-answering', 'BLEU-1 (%)'),
    ('omnimedvqa', 'medical-visual-question-answering', 'Accuracy'),
    ('gmai-mmbench', 'medical-visual-question-answering', 'Accuracy'),
    ('vqa-med-2019', 'medical-visual-question-answering', 'Accuracy'),
    ('vqa-med-2019', 'medical-visual-question-answering', 'BLEU'),
    ('vqa-med-2020', 'medical-visual-question-answering', 'Accuracy'),
    ('vqa-med-2020', 'medical-visual-question-answering', 'BLEU'),
    ('vqa-med-2021', 'medical-visual-question-answering', 'Accuracy'),
    ('vqa-med-2021', 'medical-visual-question-answering', 'BLEU'),
    ('bioasq', 'medical-question-answering', 'Accuracy'),
    ('headqa', 'medical-question-answering', 'Accuracy'),
    ('clicr', 'medical-question-answering', 'F1'),
    ('radqa', 'medical-question-answering', 'Answer F1'),
    ('cmb', 'medical-question-answering', 'Accuracy'),
    ('cmexam', 'medical-question-answering', 'Accuracy'),
    ('cmexam', 'medical-question-answering', 'Weighted F1'),
    ('medexqa', 'medical-question-answering', 'Accuracy'),
    ('medexqa', 'medical-question-answering', 'ROUGE-L'),
    ('medexqa', 'medical-question-answering', 'BLEU'),
    ('medexqa', 'medical-question-answering', 'BERTScore'),
    ('medexpqa', 'medical-question-answering', 'Accuracy'),
    ('afrimed-qa', 'medical-question-answering', 'Accuracy')
)
INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM metric_links l
JOIN tasks t ON t.slug = l.task_slug
JOIN datasets d ON d.slug = l.dataset_slug
JOIN metrics m ON m.name = l.metric_name
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

-- Move established medical-QA leaderboards from their broad parent task to
-- the precise child. Parent task pages still include child benchmarks through
-- hierarchy traversal, while each evaluation remains stored only once.
WITH moves(dataset_slug, old_task_slug, new_task_slug) AS (
    VALUES
    ('slake', 'medical-imaging', 'medical-visual-question-answering'),
    ('vqa-rad', 'medical-imaging', 'medical-visual-question-answering'),
    ('medxpertqa-mm', 'question-answering', 'medical-visual-question-answering'),
    ('medqa', 'question-answering', 'medical-question-answering'),
    ('pubmedqa', 'question-answering', 'medical-question-answering'),
    ('medmcqa', 'question-answering', 'medical-question-answering'),
    ('medxpertqa-text', 'question-answering', 'medical-question-answering')
)
INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT new_task.id, d.id, tdm.metric_id
FROM moves mv
JOIN datasets d ON d.slug = mv.dataset_slug
JOIN tasks old_task ON old_task.slug = mv.old_task_slug
JOIN tasks new_task ON new_task.slug = mv.new_task_slug
JOIN task_dataset_metrics tdm
  ON tdm.task_id = old_task.id AND tdm.dataset_id = d.id
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

WITH moves(dataset_slug, old_task_slug, new_task_slug) AS (
    VALUES
    ('slake', 'medical-imaging', 'medical-visual-question-answering'),
    ('vqa-rad', 'medical-imaging', 'medical-visual-question-answering'),
    ('medxpertqa-mm', 'question-answering', 'medical-visual-question-answering'),
    ('medqa', 'question-answering', 'medical-question-answering'),
    ('pubmedqa', 'question-answering', 'medical-question-answering'),
    ('medmcqa', 'question-answering', 'medical-question-answering'),
    ('medxpertqa-text', 'question-answering', 'medical-question-answering')
)
UPDATE evaluations e
SET task_id = new_task.id,
    updated_at = CURRENT_TIMESTAMP
FROM moves mv
JOIN datasets d ON d.slug = mv.dataset_slug
JOIN tasks old_task ON old_task.slug = mv.old_task_slug
JOIN tasks new_task ON new_task.slug = mv.new_task_slug
WHERE e.dataset_id = d.id
  AND e.task_id = old_task.id;

WITH moves(dataset_slug, old_task_slug) AS (
    VALUES
    ('slake', 'medical-imaging'),
    ('vqa-rad', 'medical-imaging'),
    ('medxpertqa-mm', 'question-answering'),
    ('medqa', 'question-answering'),
    ('pubmedqa', 'question-answering'),
    ('medmcqa', 'question-answering'),
    ('medxpertqa-text', 'question-answering')
)
DELETE FROM task_dataset_metrics tdm
USING moves mv, datasets d, tasks old_task
WHERE d.slug = mv.dataset_slug
  AND old_task.slug = mv.old_task_slug
  AND tdm.dataset_id = d.id
  AND tdm.task_id = old_task.id;

WITH moves(dataset_slug, old_task_slug) AS (
    VALUES
    ('slake', 'medical-imaging'),
    ('vqa-rad', 'medical-imaging'),
    ('medxpertqa-mm', 'question-answering'),
    ('medqa', 'question-answering'),
    ('pubmedqa', 'question-answering'),
    ('medmcqa', 'question-answering'),
    ('medxpertqa-text', 'question-answering')
)
DELETE FROM task_datasets td
USING moves mv, datasets d, tasks old_task
WHERE d.slug = mv.dataset_slug
  AND old_task.slug = mv.old_task_slug
  AND td.dataset_id = d.id
  AND td.task_id = old_task.id;

-- Benchmark source papers receive durable manual task tags.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT DISTINCT d.introducing_paper_id, td.task_id, 'manual'
FROM task_datasets td
JOIN datasets d ON d.id = td.dataset_id
WHERE td.task_id IN (
    SELECT id FROM tasks
    WHERE slug IN ('medical-question-answering', 'medical-visual-question-answering')
)
  AND d.introducing_paper_id IS NOT NULL
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

COMMIT;
