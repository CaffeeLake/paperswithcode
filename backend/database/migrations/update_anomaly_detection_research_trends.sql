-- Add the three editorial research-trend bullets shown below the Anomaly
-- Detection task description.
UPDATE tasks
SET research_trends = jsonb_build_array(
    '**From per-product normality models to foundation-model transfer.** [PatchCore](/paper/2106.08265) stores nominal patch features for category-specific detection, while [AnomalyCLIP](/paper/2310.18961) and [Crane](/paper/2504.11055) adapt frozen CLIP and DINO features with object-agnostic prompts, spatial attention, and local-to-global fusion to detect and localize anomalies in target-unseen domains.',
    '**One deployable model is replacing a bank of class-specific detectors.** [Dinomaly](/paper/2405.14325) uses loose Transformer reconstruction over foundation features, while [MambaAD](/paper/2404.06564) combines multi-scale local modeling with linear-complexity state-space layers; both target unified multi-class detection on [MVTec AD](/benchmark/mvtec-ad-unified-multi-class?task=anomaly-detection) and [Real-IAD](/benchmark/real-iad-unified-multi-class?task=anomaly-detection), narrowing the accuracy gap while reducing deployment overhead.',
    '**Evaluation is becoming protocol-specific, cross-domain, and multimodal.** [OpenOOD v1.5](/paper/2306.09301) standardizes large-scale semantic and covariate shifts, target-unseen [VisA](/benchmark/visa-zero-shot-cross-domain?task=anomaly-detection) and [MVTec AD](/benchmark/mvtec-ad-zero-shot-cross-domain?task=anomaly-detection) boards separate source adaptation from target access, and [G2SF](/paper/2503.10091) plus [MuSc-V2](/paper/2511.10047) add RGB-3D geometry—pushing beyond single-dataset image AUROC toward pixel localization and sensor robustness.'
),
updated_at = NOW()
WHERE slug = 'anomaly-detection';
