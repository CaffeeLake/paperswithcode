-- Remove reviewed image/video task overlaps where the paper covers only one
-- side of the pair. Keep the corrections narrow so unrelated task curation is
-- untouched.

DELETE FROM paper_tasks pt
USING tasks t
WHERE pt.task_id = t.id
  AND t.slug = 'image-editing'
  AND pt.paper_id = ANY (ARRAY[105873, 95076, 82902, 57576]);

DELETE FROM paper_tasks pt
USING tasks t
WHERE pt.task_id = t.id
  AND (
    (t.slug = 'image-generation' AND pt.paper_id = ANY (ARRAY[106011, 104047, 98012]))
    OR
    (t.slug = 'video-generation' AND pt.paper_id = ANY (ARRAY[106011, 104047, 57779]))
  );

DELETE FROM paper_tasks pt
USING tasks t
WHERE pt.task_id = t.id
  AND (
    (t.slug = 'image-understanding' AND pt.paper_id = ANY (
      ARRAY[104444, 104403, 98824, 98315, 92575, 83690, 83452, 57406, 57267]
    ))
    OR
    (t.slug = 'video-understanding' AND pt.paper_id = ANY (ARRAY[104739, 57247, 7450]))
  );

-- Neutral titles need explicit curation when their abstracts establish the
-- real task scope more reliably than title-based conflict resolution.
WITH reviewed(paper_id, task_slug) AS (
  VALUES
    (103952, 'image-generation'),
    (103952, 'video-generation'),
    (92602, 'image-generation'),
    (92602, 'video-generation'),
    (74206, 'image-generation'),
    (74206, 'video-generation'),
    (56548, 'image-generation'),
    (54600, 'image-generation'),
    (43569, 'image-generation'),
    (38270, 'image-generation'),
    (32818, 'image-generation'),
    (32818, 'video-generation'),
    (94555, 'image-understanding')
)
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT reviewed.paper_id, tasks.id, 'manual'
FROM reviewed
JOIN tasks ON tasks.slug = reviewed.task_slug
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';
