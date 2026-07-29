UPDATE methods
SET area_id = (
    SELECT id
    FROM areas
    WHERE name = 'Vision'
    LIMIT 1
),
updated_at = CURRENT_TIMESTAMP
WHERE slug = 'depth-anything'
  AND area_id IS DISTINCT FROM (
      SELECT id
      FROM areas
      WHERE name = 'Vision'
      LIMIT 1
  );
