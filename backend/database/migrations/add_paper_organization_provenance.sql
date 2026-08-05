-- Add authenticated HF-user provenance to manually curated paper/org links.
-- This migration is additive and safe to apply before application deployment.

BEGIN;

ALTER TABLE public.paper_organizations
    ADD COLUMN IF NOT EXISTS added_by_hf_subject VARCHAR(255),
    ADD COLUMN IF NOT EXISTS added_by_hf_username VARCHAR(255);

-- Recover attribution for existing manual links when the append-only catalog
-- audit contains the event that first introduced the association.
WITH recovered AS (
    SELECT
        po.paper_id,
        po.organization_id,
        addition.actor_hf_subject,
        addition.actor_username
    FROM public.paper_organizations AS po
    LEFT JOIN LATERAL (
        SELECT
            event.actor_hf_subject,
            event.actor_username
        FROM public.catalog_mutation_events AS event
        WHERE event.entity_type = 'paper_organizations'
          AND event.entity_id = po.paper_id::text
          AND EXISTS (
              SELECT 1
              FROM jsonb_array_elements(
                  COALESCE(event.after_snapshot->'value', '[]'::jsonb)
              ) AS association
              WHERE (association->>'organization_id')::bigint = po.organization_id
          )
          AND NOT EXISTS (
              SELECT 1
              FROM jsonb_array_elements(
                  COALESCE(event.before_snapshot->'value', '[]'::jsonb)
              ) AS association
              WHERE (association->>'organization_id')::bigint = po.organization_id
          )
        ORDER BY event.created_at, event.id
        LIMIT 1
    ) AS addition ON TRUE
    WHERE po.source = 'manual'
)
UPDATE public.paper_organizations AS po
SET
    added_by_hf_subject = recovered.actor_hf_subject,
    added_by_hf_username = recovered.actor_username
FROM recovered
WHERE po.paper_id = recovered.paper_id
  AND po.organization_id = recovered.organization_id
  AND recovered.actor_hf_subject IS NOT NULL;

COMMENT ON COLUMN public.paper_organizations.added_by_hf_subject IS
'Stable HF OAuth subject that created a manual association; null for HF-sourced or legacy links.';

COMMENT ON COLUMN public.paper_organizations.added_by_hf_username IS
'HF username that created a manual association; null for HF-sourced or unattributed links.';

COMMIT;
