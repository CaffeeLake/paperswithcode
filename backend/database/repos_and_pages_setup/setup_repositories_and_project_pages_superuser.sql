-- Superuser operations for repositories and project pages setup
-- Run this as postgres superuser for operations requiring elevated privileges

-- Add unique constraint for repositories (if not exists)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'unique_paper_repository'
        AND conrelid = 'repositories'::regclass
    ) THEN
        ALTER TABLE repositories
        ADD CONSTRAINT unique_paper_repository
        UNIQUE (paper_id, url);
        RAISE NOTICE 'Added unique constraint to repositories table';
    ELSE
        RAISE NOTICE 'Unique constraint already exists on repositories table';
    END IF;
END $$;

-- Verify constraints are in place
SELECT
    'CONSTRAINT VERIFICATION' as info,
    conname as constraint_name,
    contype as constraint_type,
    pg_get_constraintdef(oid) as definition
FROM pg_constraint
WHERE conrelid IN ('repositories'::regclass, 'project_pages'::regclass)
AND contype = 'u'  -- unique constraints only
ORDER BY conrelid::regclass::text, conname;
