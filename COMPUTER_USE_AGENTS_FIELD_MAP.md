# Computer-Use Agents field map

Research date: 2026-07-17. Binding paper scope: the first 100 papers returned by
`/api/v1/tasks/computer-use-agents/papers?order_by=trending&page_size=100&page=1`.
The reconciliation ledger is `computer-use-agents-top100-ledger.csv`.

## Scope and evidence

- Live task/API and local DB: 336 tagged papers, 25 linked benchmarks, 221 task
  evaluation rows at stocktake time. In the live top 100, 32 papers had at least
  one task eval and 68 had none.
- Recent slice: 39 top-100 papers are from 2026 and 43 are from 2025.
- Semantic Scholar: 661 deduplicated relevant candidates and 564 broad 2025/26
  candidates across task and benchmark aliases.
- Legacy PwC: no coherent computer-use leaderboard; the useful historical leads
  are ScreenSpot (18 rows), one Mind2Web row, and comparator-heavy WebLINX rows.
- GitHub: 241 relevant repositories; strongest official signals include
  OmniParser, Agent-S, UI-TARS, MobileAgent, Fara, OSWorld, ShowUI, WebArena,
  BrowserGym, Mind2Web, AndroidWorld, OpenCUA, SeeClick, OS-Atlas, and UGround.
- Hugging Face: 285 distinct papers and 347 model/dataset artifact search results;
  exact official open-weight evidence was retained only where the source ties the
  artifact to the evaluated variant.
- Comparison-table expansion: OSWorld, WebArena, Mind2Web, grounding, mobile,
  and safety lineages were followed to produce the paper worklist. Comparator
  scores are leads only and are not importable by default.

## Benchmark families and contracts

| Family | Canonical benchmarks | Metric / contract | Key incompatibilities |
|---|---|---|---|
| Desktop/OS execution | OSWorld, OSWorld-Verified, OSWorld 15/50/100-step, OSWorld 2.0, Windows Agent Arena | Task success rate | Version, task subset, VM image, verifier, observation/action space, and step budget must remain explicit. |
| Web execution | WebArena, VisualWebArena, WorkArena, WebVoyager, Online-Mind2Web, WebTailBench, DeepShop, Odysseys | Task success rate or benchmark-native score | Live site/snapshot, evaluator, visual vs DOM observation, and BrowserGym constituent protocols cannot be merged. |
| Offline web prediction | Mind2Web, WebLINX | Element/action/step or conversational scores | Offline prediction is not live task success; Mind2Web splits and WebLINX history/input settings differ. |
| Mobile execution | AndroidWorld, MobileWorld, AndroidControl, AITW/GUIOdyssey | Task success or benchmark-native action accuracy | Dynamic emulator success, offline action matching, task subset, and device/app snapshots differ. |
| Static GUI grounding | ScreenSpot, ScreenSpot-v2, ScreenSpot-Pro, OSWorld-G, UI-Vision, MMBench-GUI | Point-in-box/click accuracy | Benchmark generations, element/platform subsets, coordinate vs box output, zoom, and structured-UI access must remain separate. |
| Hybrid/recent | WeaveBench, MCPWorld, CUA-Gym environments | Benchmark-native task success | These are new protocols, not aliases for OSWorld/WebArena. |
| Safety/security | OS-Harm, RiOSWorld, SafeArena, ST-WebAgentBench, VPI-Bench | Harm/refusal/attack/policy metric | Metric direction and safety semantics differ from ordinary capability success. |

## Major papers and lineages

- Historical anchors: Mind2Web, WebArena, AgentBench, OSWorld, CogAgent,
  VisualWebArena, SeeClick, WebVoyager, AndroidWorld, WorkArena, WebLINX,
  Windows Agent Arena, and OmniACT.
- Grounding lineage: SeeClick -> UGround -> OS-ATLAS -> ShowUI/UI-TARS ->
  ScreenSpot-Pro -> GUI-R1/UI-R1/InfiGUI/GUI-Actor/ScaleCUA.
- Desktop lineage: OSWorld -> Agent S -> UI-TARS -> Agent S2 -> OpenCUA ->
  Mobile-Agent/GUI-Owl -> ScaleCUA/EvoCUA/CUA-Gym -> OSWorld 2.0.
- Web lineage: WebArena/VisualWebArena -> WebVoyager -> BrowserGym/WorkArena ->
  WebRL/AgentLab/SkillWeaver -> Online-Mind2Web/Fara/WebTailBench.
- Mobile lineage: AppAgent/AITW -> AndroidWorld -> GUIOdyssey/Mobile-Agent ->
  MobileWorld/GUI-Owl/MobileForge.
- Important 2026 slice: CUA-Skill, ToolCUA, UI-Venus-1.5, EvoCUA,
  Mobile-Agent-v3.5, ClawGUI, CUA-Gym, WeaveBench, OSWorld 2.0, Fara-1.5,
  UI-MOPD, MobileForge, and MemGUI-Agent/Bench.

## Benchmark decision table

| Benchmark group | Current DB state | Evidence | Decision |
|---|---|---|---|
| OSWorld family | Present; core rows, but OSWorld-Verified lacks source metadata | Live DB, papers, HF/GitHub, comparison tables | Wave 1 repair/import; verify every version and step budget separately. |
| ScreenSpot family | Present and heavily populated | Legacy, live DB, HF cards, comparison tables | Wave 1 import/verify; never merge v1/v2/Pro. |
| AndroidWorld | Present and populated | Source paper, live DB, HF/GitHub | Wave 1 import/verify. |
| WebArena | Present but source URL is non-native and metric/protocol needs audit | Citation, GitHub, source paper | Wave 1 repair/import/verify. |
| WebVoyager / Online-Mind2Web | Present | Live DB, Fara/UI-TARS tables | Wave 1 import/verify. |
| Windows Agent Arena | Present but source metadata missing | Source paper, GitHub, comparison tables | Wave 1 repair/import/verify. |
| OSWorld-G / UI-Vision / MMBench-GUI | Present; latter two have external source wiring gaps | Grounding papers/cards | Wave 1 repair/import/verify. |
| VisualWebArena / WorkArena | Missing from task benchmark stocktake | Citations, GitHub, WebArena/BrowserGym tables | Wave 2 add as distinct benchmarks, then import native rows. |
| Mind2Web offline / WebLINX | Missing or not task-linked | Legacy, citations, source papers | Wave 2 add with explicit metric/split contracts; do not copy comparator rows. |
| MobileWorld / OSWorld 2.0 / WeaveBench | MobileWorld and OSWorld 2.0 present; WeaveBench missing | 2025/26 papers and artifacts | Wave 2 recent coverage; separate new protocols. |
| Safety benchmarks | Missing from task stocktake | 2025/26 safety papers and repos | Wave 3, only with benchmark-specific metric direction. |

## Main risks

- Existing rows may be comparator-sourced or attached to a later comparison paper;
  each leaderboard requires paper-native verification.
- Existing OSWorld rows mix original, Verified, internal implementations, task
  subsets, and 15/50/100-step budgets.
- Some ScreenSpot-Pro results use zoom/verifier variants; names and methodology
  must retain the setup.
- Proprietary foundation models default to closed even when their agent scaffold
  is public. Conversely, official reproducible GitHub releases can justify open
  rows without an HF URL.
- BrowserGym is an ecosystem/harness, not a single homogeneous benchmark.
- Safety scores can reverse direction depending on whether they measure attack or
  defense success.

## Completion snapshot

- The fixed live top-100 sample was inspected paper by paper. Final ledger
  decisions: 46 `imported`, 20 `already-covered`, 10
  `defer-missing-benchmark`, 10 `not-a-results-paper`, 9
  `defer-not-comparable`, and 5 `defer-not-paper-native`.
- 66 of the top 100 papers now have task evaluation rows, totaling 242 rows.
  The whole task currently has 322 evaluation rows from 99 papers across 37
  populated benchmark pages.
- 166 newly allocated evaluation rows survived verification, spanning 50 papers
  and 27 benchmark pages. Rows removed during verification remain explained in
  the top-100 ledger rather than silently disappearing from the paper audit.
- Twelve reusable protocol variants were created for WindowsAgentArena horizons,
  OSWorld/OSWorld-Verified task-set and horizon combinations, refined OSWorld-G,
  and the 117-task MobileWorld GUI-only split. Paper-specific one-off protocols
  were deferred rather than creating single-row benchmark pages.
- WebArena was rewired from the incorrect `Score (0-10)` label to percentage-scale
  `Success Rate`. OSWorld 2.0 partial score was kept separate from strict binary
  success, and AndroidControl was standardized to the High/OOD joint step-success
  protocol.
- Final metric validation reports no Computer Use Agents mismatches and no missing
  `best_metric` values. Four unrelated pre-existing mismatches remain elsewhere in
  the database (ETH3D relative, FLORES-101, FLORES-200 devtest, and Livebench).
