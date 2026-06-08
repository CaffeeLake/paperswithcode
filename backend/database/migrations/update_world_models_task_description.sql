-- Append Fei-Fei Li explainer link to world models task description.
UPDATE tasks
SET
    description = description || ' See also [Fei-Fei Li''s post](https://x.com/drfeifei/status/2062247238143996275) which explains the different definitions of world models.',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'world-models';
