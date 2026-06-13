-- Expand Neural Audio Codec description with motivation for compression.

UPDATE methods
SET
    description = 'A neural audio codec uses learned encoder–decoder models to compress audio into a compact representation and reconstruct it at decode time, often replacing handcrafted stages in classical codecs. That compression reduces bandwidth and storage for streaming, telephony, and on-device playback, and yields compact codes that are easier to transmit or feed into downstream speech and audio models. Implementations may use continuous latents, vector quantization, or other bottlenecks depending on bitrate and latency needs. [SoundStream](/methods/soundstream) is a widely used example for low-latency speech and general audio.',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'neural-audio-codec';
