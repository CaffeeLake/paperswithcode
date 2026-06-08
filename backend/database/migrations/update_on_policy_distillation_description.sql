-- Update on-policy distillation method description with explainer link.
UPDATE methods
SET
    description = 'On-policy distillation is a post-training method where a student model samples from its own current policy and receives a teacher signal on those on-policy states. It combines the dense supervision of distillation with the locality of online reinforcement learning, which can help the student learn task behavior while staying closer to the regions of the distribution it already visits. It''s recommended to watch [Sasha Rush''s video lecture](https://x.com/dwarkesh_sp/status/2062353335529935114) to understand how this works.',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'on-policy-distillation';
