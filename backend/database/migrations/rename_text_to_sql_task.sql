-- Use community casing: title-case "Text-to", capitalized acronym "SQL".
UPDATE tasks
SET
    name = 'Text-to-SQL',
    keywords = 'Text-to-SQL,text to sql,semantic parsing,sql generation,spider',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'text-to-sql';
