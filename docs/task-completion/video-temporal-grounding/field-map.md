# Video Temporal Grounding field map

## Completion contract

Thoroughly map the field's major benchmarks, major papers, comparison-paper graph,
and paper-native evaluations. Reconcile the top 100 papers on the live task page:
every paper must end with verified evaluation rows or an evidence-backed ledger
decision.

## Initial live state

- Task: `video-temporal-grounding` (ID 430), a child of `video-understanding`.
- Live papers: 135; frozen top-100 slice is recorded in
  [`top100-ledger.csv`](top100-ledger.csv).
- Existing directly linked benchmarks: 0.
- Existing task-scoped evaluation rows: 0.
- Only one top-100 paper currently has evaluation rows elsewhere in the database;
  none are yet attached to this task.
- Top-100 year slice: 23 papers from 2025, 10 from 2026, 40 from 2019–2024,
  and 27 recent records whose publication date is not yet populated locally.

## Research surfaces

The seven required surfaces were reconciled before database writes:

1. **Live task page and local DB.** The frozen live top 100 contains the historical
   specialist line, recent video-LLM systems, benchmark papers, surveys/libraries,
   adjacent spatio-temporal grounding papers, and several keyword false positives.
   The task initially had no benchmarks or evals. Only CharadesSTA and ActivityNet
   Captions existed locally; both were attached to broad Video Understanding with
   inadequate generic metric wiring.
2. **Semantic Scholar.** Citation and recent searches recover the historical core:
   TALL/CTRL (1705.02101), 2D-TAN (1912.03590), LGI (2004.07514), QVHighlights /
   Moment-DETR (2107.09609), UMT (2203.12745), UniVTG (2307.16715), and the later
   video-LLM line. Citation counts are discovery signals, not score provenance.
3. **Legacy PwC.** The 236 MB evaluation dump was streamed with `ijson`, never
   loaded whole. Consolidating six task aliases yields 114 distinct result rows,
   77 dataset-paper pairs, and 43 source-paper identities. The retained core is
   QVHighlights (41 rows), Charades-STA (36), TACoS (12), ActivityNet Captions (9),
   MAD (8), Ego4D-NLQ (7), and DiDeMo (1).
4. **GitHub.** Strong reproducibility signals include UniVTG (380 stars),
   Moment-DETR (349), EgoVLP (261), DiDeMo source code (198), TimeLens (159),
   LGI (132), VTG-LLM (130), VSLNet (113), VTG-GPT (112), and newer official
   repos for TimeLens2, OmniVTG, TaRO, VideoSearch-R1, and MomentSeeker.
5. **Hugging Face.** Exact paper/release linkage is strongest for TimeLens,
   TimeLens2, OmniVTG, TaRO, Vidi/Vidi2, VideoSearch-R1, VideoMind, TRACE,
   VideoTG-R1, and VTG-LLM. Dataset signals strongly support TimeLens-Bench and
   MomentSeeker; sparse HF presence for classic datasets is not evidence of low
   importance.
6. **Comparison tables.** Recurring specialist comparators include CTRL/TALL,
   MCN, ACRN, ROLE, VAL, ACL-K, MAN, QSPN, SM-RL, SLTA, ABLR, SAP, TripNet,
   TGN, CMIN, 2D-TAN, VSLNet, Moment-DETR, UniVTG, and R2-Tuning. The video-LLM
   cluster repeatedly compares TimeChat, VTimeLLM, Momentor, HawkEye, VTG-LLM,
   TRACE, Grounded-VideoLLM, LLaVA-ST, UniTime, VideoMind, Time-R1, TimeSuite,
   TimeLens, and TimeLens2. Comparator cells are discovery leads only; they are
   not imported as external evals.
7. **Explicit 2025/2026 checklist.** High-priority recent results/source papers
   include Time-R1, LLaVA-ST, VideoMind, SpaceVLLM, UniTime, TimeLens, TimeLens2,
   MomentSeeker, Vidi/Vidi2.5, OmniVTG, TaRO, VideoSearch-R1, VideoTG-R1, and
   other top-100 papers whose primary tables survive protocol checks.

## Candidate benchmark families

The benchmark waves are:

- classic single-span temporal sentence grounding: Charades-STA, ActivityNet Captions,
  TACoS, DiDeMo;
- moment retrieval and highlight detection: QVHighlights;
- subtitle/movie and corpus retrieval: TVR and MAD;
- egocentric natural-language queries: Ego4D-NLQ;
- quality-refined MLLM evaluation: Charades-TimeLens, ActivityNet-TimeLens,
  QVHighlights-TimeLens;
- long-video and multimodal retrieval: MomentSeeker, VUE-TR, VUE-TR-V2;
- spatio-temporal grounding benchmarks, which may require a separate task/protocol
  rather than being merged into temporal-only interval leaderboards.

## Known comparability risks

- Original datasets and TimeLens re-annotations are different leaderboards.
- VUE native multimodal AUC metrics differ from TimeLens2's vision-only R1/mIoU
  protocol.
- MomentSeeker full multimodal retrieval, text-only generation, and differing IoU
  thresholds must not be merged.
- QVHighlights moment retrieval and highlight detection use different metrics.
- Ego4D-NLQ versions, splits, R@K thresholds, and MLLM single-output protocols need
  explicit contracts.
- Spatio-temporal tube grounding and temporal-only interval grounding are not directly
  comparable.
- Supervised/fine-tuned and zero-shot results must be labeled and should not be
  silently pooled when the prompt or training protocol changes the task contract.
- ActivityNet Captions retrieval must be separated from dense captioning; val1,
  val2, and test cannot be mixed.
- TACoS/TACoS-STA thresholds and feature regimes vary substantially across eras.
- MAD is corpus-level long-video retrieval, unlike single-video localization.
- DiDeMo uses a fixed temporal grid rather than free-boundary localization.
- Multi-segment/one-to-many grounding cannot be forced onto single-interval boards.

## Benchmark selection table

| Wave | Benchmark contract | Decision |
|---|---|---|
| 1 | Charades-STA temporal localization | Add/repair; source TALL/CTRL 1705.02101; threshold-specific R@K and mIoU |
| 1 | ActivityNet Captions temporal localization | Reuse/repair dataset but create task-specific grounding metric contract; source 1705.00754 |
| 1 | QVHighlights moment retrieval | Add; source 2107.09609; keep MR separate from highlight detection and preserve split |
| 1 | TACoS temporal localization | Add; source 1403.6173; threshold-specific metrics |
| 1 | Ego4D-NLQ | Add; source 2110.07058; version and split explicit |
| 1 | MAD corpus moment retrieval | Add; source 2112.00431; corpus-retrieval R@K contract |
| 1 | DiDeMo | Add; source 1708.01641; fixed-grid protocol explicit |
| 2 | Charades-TimeLens | Add separately from Charades-STA; source 2512.14698 |
| 2 | ActivityNet-TimeLens | Add separately from ActivityNet Captions; source 2512.14698 |
| 2 | QVHighlights-TimeLens | Add separately from original QVHighlights; source 2512.14698 |
| 2 | MomentSeeker native and text-only subset | Add only as separately named protocol contracts |
| 2 | VUE-TR/V2 native and vision-only subsets | Add only as separately named modality/protocol contracts |
| 3 | OmniVTG / other new open-world or multi-segment sets | Defer until source protocol and multi-paper adoption are established |
| Exclude | HC-STVG, VidSTG, TubeDETR/OmniSTVG tube metrics | Adjacent spatio-temporal grounding; not comparable to temporal-only intervals |

The field-map gate is **passed** for Waves 1 and 2. Dataset creation still requires
source-paper resolution and exact metric/split verification benchmark by benchmark.

## Historical and recent paper map

- **Foundational/source papers:** TALL/CTRL, DiDeMo, ActivityNet Captions,
  QVHighlights/Moment-DETR, Ego4D, MAD, TVR, MomentSeeker, TimeLens, Vidi/Vidi2,
  and TimeLens2.
- **Classical specialist line:** 2D-TAN, LGI, VSLNet, DRN, VLG-Net, MMN,
  Moment-DETR, UMT, QD-DETR, CG-DETR, UVCOM, BAM-DETR, RGNet, SG-DETR,
  FlashVTG, and LD-DETR.
- **Unified and long-video line:** UniVTG, UnLoc, UniMD, EgoVLP/EgoVLPv2,
  corpus moment retrieval, and egocentric NLQ systems.
- **Video-LLM line:** TimeChat, HawkEye, VTG-GPT, VTG-LLM, TRACE,
  Grounded-VideoLLM, LLaVA-ST, VideoMind, Time-R1, UniTime, TimeLens,
  TimeLens2, VideoSearch-R1, OmniVTG, and TaRO.
- **Top-100 exclusions/defer classes:** surveys and reproducibility libraries are
  `not-a-results-paper`; E-SQL, Found-RL, Sonar-TS, and unrelated activity/retrieval
  matches are false positives; tube/box grounding is `defer-not-comparable`; a
  paper without a native table for an existing contract is
  `defer-not-paper-native` or `defer-missing-benchmark` as appropriate.
