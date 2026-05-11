-- Frontend v2 migration: insert 3 canonical Method rows that the v2 figure-resolution
-- dictionary expects (PLAN.md §4.3).
--
-- The v2 MethodDetailView uses a 3-tier fallback for the figure:
--   1. Hand-drawn SVG keyed by canonical slug (Transformer, Attention, CNN, U-Net,
--      MoE, Diffusion, GAN, VAE, RLHF).
--   2. method.image_url (covers ~95% of methods in the live DB).
--   3. GenericFig.
--
-- Of the canonical slugs, two currently have no Method row in the DB:
--   - attention
--   - mixture-of-experts
--
-- This file inserts fully-curated stubs for those two so tier 1 fires for them. The
-- `image_url` is left NULL so the dictionary figures win unimpeded. `paper_count` is
-- not a column on `methods` (it's computed at query time), so we don't set it. The
-- existing keyword-matching CRON pipeline picks up paper associations via `keywords`
-- once those are added later via the admin UI. `area_id` is resolved via subquery on
-- `areas.name` for robustness (the FK target is stable; Area IDs vary per env).
--
-- Idempotent: ON CONFLICT (slug) DO NOTHING. Safe to re-run.

INSERT INTO methods (slug, name, full_name, description, area_id, introduced_year, source_url, source_title, image_url)
VALUES
  ('attention',
   'Attention',
   'Attention Mechanism',
   'A mechanism that allows neural networks to focus on different parts of the input when producing each part of the output. Introduced for neural machine translation, attention computes a weighted sum of input representations where the weights are learned functions of a query.',
   (SELECT id FROM areas WHERE name = 'Natural Language Processing'),
   2014,
   'https://arxiv.org/abs/1409.0473',
   'Neural Machine Translation by Jointly Learning to Align and Translate',
   NULL)
ON CONFLICT (slug) DO NOTHING;

INSERT INTO methods (slug, name, full_name, description, area_id, introduced_year, source_url, source_title, image_url)
VALUES
  ('mixture-of-experts',
   'Mixture of Experts',
   'Mixture of Experts (MoE)',
   'An architecture where a sparse gating mechanism routes each input token to a small subset of expert subnetworks, dramatically increasing model capacity without proportional compute cost. Modern variants (e.g., Switch Transformer, GShard) are foundational to large-scale language model scaling.',
   (SELECT id FROM areas WHERE name = 'General'),
   2017,
   'https://arxiv.org/abs/1701.06538',
   'Outrageously Large Neural Networks: The Sparsely-Gated Mixture-of-Experts Layer',
   NULL)
ON CONFLICT (slug) DO NOTHING;
