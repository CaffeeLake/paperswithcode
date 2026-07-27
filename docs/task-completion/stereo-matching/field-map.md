# Stereo Matching field map

Research snapshot: 2026-07-21 UTC. Task: `stereo-matching` (`tasks.id=324`).

## Completion contract

This pass covers the live task page's full inventory: 87 papers (the page has fewer than 100). Every paper must finish with verified evaluation rows or an evidence-backed ledger decision. Evaluation imports are paper-native only; comparison-table baselines are discovery leads, not importable rows for another paper.

## Seven-surface map

### 1. Live page and local database

- The live API returns 87 papers and no second page.
- The task initially had zero `task_datasets`, zero configured metrics, and zero stereo evaluation rows.
- All 87 papers therefore began as zero-eval papers for Stereo Matching. CroCo v2 and EMatch had only optical-flow evaluations elsewhere.
- 44/87 papers had linked repository/project evidence. The explicit recent slice contains 45 papers from 2025/2026 after source-ID/venue inference.
- Highest-signal gaps include Scene Flow/DispNet, PSMNet, RAFT-Stereo, AANet, CREStereo, IGEV, UniMatch, HITNet, FoundationStereo, DEFOM-Stereo, and Fast-FoundationStereo.

### 2. Semantic Scholar

- Eight searches (four broad and four 2025/2026 variants) yielded 800 raw hits and 573 deduplicated candidates; 476 survived a broad title/abstract relevance filter.
- Top-cited field anchors include Scene Flow/DispNet (1512.02134), PSMNet (1803.08669), MC-CNN (1510.05970), GA-Net (1904.06587), RAFT-Stereo (2109.07547), AANet (2004.09548), LEAStereo (2010.13501), CREStereo (2203.11483), IGEV (2303.06615), CFNet (2104.04314), DeepPruner (1909.05845), ACVNet (2203.02146), and HITNet (2007.12140).
- Priority 2025/2026 papers include FoundationStereo, DEFOM-Stereo, Stereo Anywhere, Stereo Any Video, S2M2, Fast-FoundationStereo, Lite Any Stereo/LAS2, SMoE-Stereo, RobuSTereo, and StereoCarla.

### 3. Legacy Papers With Code dump

- Exact legacy `Stereo Matching` nodes were empty. Relevant data lived under `Stereo Depth Estimation` and `Stereo Disparity Estimation`.
- Streaming extraction found 28 rows across 8 task-dataset tables and 14 unique source papers.
- Populated families: Scene Flow/sceneflow, KITTI 2012, KITTI 2015/KITTI2015, Middlebury 2014, and Spring.
- Spring entries for pre-2023 papers are benchmark-server re-evaluations, not paper-native cells. Legacy metric aliases and missing split metadata require source verification.

### 4. GitHub popularity and release evidence

- Major official repositories include FoundationStereo (2824 stars), PSMNet (1547), Fast-FoundationStereo (1300), RAFT-Stereo (1099), OpenStereo (922), IGEV (679), CREStereo (627), GA-Net (561), AANet (559), ACVNet (484), Stereo Any Video (395), IGEV++ (313), S2M2 (301), DEFOM-Stereo (283), and Stereo Anywhere (278).
- Official code, weights, or reproducibility scripts generally justify `is_open=true` even when no exact HF model URL exists.
- OpenStereo is a framework/reproduction surface. Its reproduced comparator numbers remain OpenStereo experiments and cannot be reassigned as paper-native rows.

### 5. Hugging Face artifacts

- Exact official links include `nvidia/c-fast-foundationstereo`, `nvidia/ffs_stereo4d`, and S2M2's official README link to `minimok/s2m2`.
- S2M2's public weights match its Booster model but explicitly differ from its Middlebury/ETH3D submissions; row-level HF links must reflect that.
- Search mainly found third-party mirrors for RAFT/IGEV/CREStereo/FoundationStereo. These are not eligible row-level model links without official source ties.
- GitHub/Drive releases dominate this field, so absent HF metadata is not evidence that a model is closed.

### 6. Comparison-table expansion

- FoundationStereo expands to CREStereo++, DSMNet, Mask-CFNet, HVT-RAFT, RAFT-Stereo, Selective-IGEV, IGEV/IGEV++, Former-RAFT-DAM, NMRF, LEAStereo, GA-Net, ACVNet, CroCo-Stereo, GMStereo, HITNet, and MoCha-Stereo.
- LAS2 and Fast-FoundationStereo expand the recent efficiency/generalization line to FoundationStereo, Stereo Anywhere, DEFOM, MonSter, LightStereo, BANet, RT-IGEV, PromptStereo, S2M2, HITNet, AANet, StereoBase, and DynamicStereo.
- Older tables repeatedly identify MC-CNN, GC-Net, PSMNet, GA-Net, GwcNet, DeepPruner, AANet, LEAStereo, HITNet, CFNet, RAFT-Stereo, CREStereo, ACVNet, and IGEV as the historical spine.
- DynamicStereo introduces a separate temporal contract (TEPE and temporal bad-pixel metrics); it is not comparable to static stereo-pair rows.

### 7. Explicit 2025/2026 check

- 45 live papers are identifiable as 2025/2026 work; all initially had zero stereo evals.
- Core recent result papers target the four-dataset zero-shot suite (Middlebury/ETH3D/KITTI12/KITTI15), Booster, DrivingStereo weather, or temporal video benchmarks.
- Dataset-only, generation/synthesis, restoration, event/asymmetric, endoscopic, omnidirectional, satellite, tactile, and MVS papers are explicitly adjudicated in `top100-ledger.csv`; they are not forced onto generic rectified-stereo leaderboards.
- RobustSpring (2025 paper, ICLR 2026) is a major emerging robustness benchmark, but its corruption-delta protocol must remain separate from ordinary Spring stereo.

## Benchmark families and contracts

| Benchmark candidate | Canonical contract | Source | Evidence | Wave | Decision |
|---|---|---|---|---|---|
| Scene Flow Stereo Test | Official train/test; EPE; confirm full Scene Flow/FlyingThings3D protocol | 1512.02134 | live, legacy, citations, comparisons, repos | 1 | import |
| KITTI 2012 Stereo Test | Hidden test; 3px Out-Noc as primary; do not mix 2px/5px or reflective subset | Geiger et al. 2012 | official server, live, legacy, comparisons | 1 | import |
| KITTI 2015 Stereo Test | Hidden test; D1-all, all pixels | Menze & Geiger 2015 | official server, live, legacy, comparisons | 1 | import |
| Middlebury v3 Stereo Test (H, nonocc) | Hidden test; half-resolution submission; Bad 2.0; non-occluded | Scharstein et al. 2014 | official site, live, legacy, comparisons | 1 | import |
| ETH3D Low-res Two-view Test (nonocc) | Hidden test; non-occluded; Bad 1.0 | Schöps et al. 2017 | official site, live, comparisons | 1 | import |
| Middlebury 2014 Zero-Shot (H, nonocc) | Public training scenes; half resolution; target-domain excluded; BP-2 | Scharstein et al. 2014 | recent comparison tables | 1 | import as distinct protocol |
| ETH3D Zero-Shot | Public training scenes; target-domain excluded; BP-1 | Schöps et al. 2017 | recent comparison tables | 1 | import as distinct protocol |
| KITTI 2012 Zero-Shot | Public training split; target-domain excluded; D1 | Geiger et al. 2012 | recent comparison tables | 1 | import as distinct protocol |
| KITTI 2015 Zero-Shot | Public training split; target-domain excluded; D1 | Menze & Geiger 2015 | recent comparison tables | 1 | import as distinct protocol |
| Booster-Q Zero-Shot | Quarter resolution; non-Lambertian subset; BP-2 primary | 2301.08245 | recent papers, official project | 2 | import |
| Spring Stereo Test | Official stereo test; 1px total; preserve sky/dense evaluation | Spring (CVPR 2023) | official site, legacy leads, current papers | 2 | import when native rows exist |
| DrivingStereo Weather Zero-Shot | Full resolution; held-out Cloudy/Foggy/Rainy/Sunny; D1 | DrivingStereo | LAS2/recent papers | 2 | import |
| Dynamic Replica Video Stereo | Official temporal test; TEPE plus stated bad-pixel metric | 2305.02296 | live, comparison tables | 2 | import |
| RobustSpring Stereo | Corruption robustness delta protocol, separate from Spring | 2505.09368 | official site, recent check | 3 | defer until repeated native rows |
| Stereo Anywhere LayeredFlow/MonoTrap | Specialized non-Lambertian/illusion protocols | Stereo Anywhere | recent paper/repo | 3 | defer pending benchmark worker evidence |
| StereoCarla | 2025 generalizable-driving dataset | 2509.12683 | live, OpenStereo | 3 | defer pending adoption/protocol review |

## Major paper waves

Wave 1 source workers: PSMNet, AANet, RAFT-Stereo, CREStereo, IGEV, IGEV++, FoundationStereo, Fast-FoundationStereo, LAS2, Scene Flow/DispNet, HITNet, CroCo v2, OpenStereo/StereoBase, DEFOM-Stereo, and current recurring live comparators.

Wave 2 expansion: MC-CNN, GC-Net, GA-Net, GwcNet, DeepPruner, LEAStereo, CFNet, ACVNet, MobileStereoNet, NMRF, Selective-Stereo, MoCha-Stereo, Stereo Anywhere, Stereo Any Video, S2M2, LightStereo, BANet, and other real result papers from the live 87-paper ledger.

## Principal risks

- Hidden test vs public train/validation is the largest comparability risk.
- Middlebury resolution and occlusion mask materially change scores.
- KITTI 2012 thresholds and KITTI 2015 D1 semantics must not be collapsed.
- Scene Flow Cleanpass/Finalpass and full family/FlyingThings subset require source confirmation.
- Zero-shot target-domain exclusion and in-domain fine-tuning require separate leaderboards.
- RVC is a composite mixed-training protocol, not an ordinary per-dataset row.
- Public checkpoint identity may differ from the paper submission (confirmed for S2M2).
- Training corpora (FSD, FFS-Stereo4D, CREStereo, TartanAir) are not leaderboards by default.
- Comparator and benchmark-server re-evaluations are excluded unless the evaluated paper itself reports the row.

## Evidence artifacts

- `top100-ledger.csv`: full 87-paper reconciliation contract.
- `paper-worklist.csv`: source-paper queue and candidate benchmark mapping.
- Scratch research: `/tmp/stereo-matching/live-db-report.md`, `legacy-report.md`, `external-report.md`, and `comparison-expansion.md`.
