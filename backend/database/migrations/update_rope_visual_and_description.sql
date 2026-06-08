-- Add RoPE method visual from Martin Krasser's explainer and link the HF blog in the description.
UPDATE methods
SET
    description = 'Rotary Position Embedding (RoPE) adds positional information to Transformer models by rotating query and key vectors inside the self-attention mechanism. Instead of adding positional vectors to token representations, RoPE rotates paired vector dimensions by a position-dependent angle, so query-key dot products naturally encode relative distance between tokens.

**Recommended read:** [You could have designed state of the art positional encoding](https://huggingface.co/blog/designing-positional-encoding).',
    image_url = 'https://krasserm.github.io/notebooks/2022-12-13-rotary-position-embedding/overview.png',
    image_credit = '[A gentle introduction to Rotary Position Embedding - Martin Krasser](https://krasserm.github.io/2022/12/13/rotary-position-embedding/)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'rope';
