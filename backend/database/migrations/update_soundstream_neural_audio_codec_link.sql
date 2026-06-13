-- Link SoundStream description to the Neural Audio Codec method page.

UPDATE methods
SET
    description = 'SoundStream is an end-to-end [neural audio codec](/methods/neural-audio-codec) that jointly trains a fully convolutional encoder/decoder with a residual vector quantizer (RVQ) using reconstruction and adversarial losses. A single model supports variable bitrates from 3–18 kbps via quantizer dropout, runs with low latency on mobile CPUs, and can jointly compress and enhance audio (e.g. background noise suppression) without extra delay. At 24 kHz, SoundStream at 3 kbps outperforms Opus at 12 kbps in subjective tests and approaches EVS at 9.6 kbps.',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'soundstream';
