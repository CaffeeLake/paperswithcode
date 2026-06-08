UPDATE tasks
SET
    image_url = 'https://paperswithcode.co/images/tasks/agents.png',
    image_credit = '[Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'agents';
