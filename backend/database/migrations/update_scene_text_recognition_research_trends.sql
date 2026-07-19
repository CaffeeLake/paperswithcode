UPDATE tasks
SET research_trends = jsonb_build_array(
    '**From convolutional sequence recognizers to pretrained vision-language readers.** [CRNN](/paper/1507.05717) made lexicon-free recognition an end-to-end CNN-RNN-CTC problem; [TrOCR](/paper/2109.10282) replaced that stack with pretrained image and text Transformers, and [CLIP4STR](/paper/2305.14014) now adapts large-scale image-text pretraining through visual prediction and cross-modal refinement.',
    '**Accuracy is being paired with simpler, faster decoding.** [PARSeq](/paper/2207.06966) unifies autoregressive, non-autoregressive, and iterative refinement with parallel token processing, while [SVTR](/paper/2205.00159) removes sequence modeling entirely and [SVTRv2](/paper/2411.15858) restores linguistic context to a CTC recognizer without adding inference cost.',
    '**Progress is shifting from saturated legacy tests toward harder data and stronger pretraining.** [Revisiting STR](/paper/2307.08723) found that ensembles miss only 2.91% of the six common benchmarks and introduced the challenge-driven [Union14M-Benchmark](/benchmark/union14m-benchmark?task=scene-text-recognition); newer work closes real/synthetic gaps through text-only decoder pretraining in [DPTR](/paper/2408.05706) and diverse simulation plus self-evolution in [UnionST](/paper/2602.06450).'
),
updated_at = NOW()
WHERE slug = 'scene-text-recognition';
