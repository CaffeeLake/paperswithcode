-- Add the three editorial research-trend bullets shown below the Omni Models
-- task description.
UPDATE tasks
SET research_trends = jsonb_build_array(
    'Omni models are moving beyond modality-specific pipelines toward native any-to-any systems. [Perceiver IO](/paper/2107.14795) established a common interface for structured inputs and outputs, [Chameleon](/paper/2405.09818) made early-fused image and text tokens generative in arbitrary sequences, and [Qwen3-Omni](/paper/2509.17765) extends the pattern to text, image, audio, and video with a Thinker-Talker mixture-of-experts architecture.',
    'Real-time, full-duplex interaction is becoming the systems frontier. [Qwen3-Omni](/paper/2509.17765) streams speech through discrete codecs and a lightweight causal decoder, [MiniCPM-o 4.5](/paper/2604.27393) aligns simultaneous perception and response on a shared temporal axis, and [OmniZip](/paper/2511.14582) makes long audio-video streams more practical through training-free cross-modal token pruning.',
    'Performance gains increasingly come from modality-balanced data and post-training rather than scale alone. [Align Anything](/paper/2412.15838) introduced 200k all-modality preference examples with language feedback, [Lance](/paper/2605.18678) uses staged objectives and adaptive data scheduling, and [Qwen3.5-Omni](/paper/2604.15804) combines specialist and on-policy distillation, curated long-context data, and interaction-aligned reinforcement learning.'
),
updated_at = NOW()
WHERE slug = 'omni-models';
