# Embedding bakeoff human-annotation release evidence

Date: 2026-07-18 UTC

## Outcome

The completed 5,000-paper bakeoff now has a reproducible human-annotation and
scoring workflow. Exactly one private Hugging Face Dataset was created:

- Dataset: <https://huggingface.co/datasets/nielsr/paperswithcode-relevance-judgments>
- pinned revision: `924febd6a2de42f450cce9cc20fab9909aeadd32`
- revision URL: <https://huggingface.co/datasets/nielsr/paperswithcode-relevance-judgments/tree/924febd6a2de42f450cce9cc20fab9909aeadd32>
- visibility: private
- Hub files: 34 including Hub `.gitattributes`; 6,238,606 bytes

The environment-selected fine-grained token authenticated as `nielsr` and had
user-namespace `repo.write`. No credential value or alternate stored token was
read or printed. A second identical upload produced no commit, confirming the
sync is idempotent. A clean download at the pinned revision passed all 31
payload checksums.

No real human labels were created. No production model winner is declared. No
Job, Bucket, Space, endpoint, scheduled Job, application database, production
feature, migration, deployment, service, or full-corpus run was changed.

## Corrected model contract

`codefuse-ai/F2LLM-v2-80M` at revision
`f4a16a11c9f5c8c7e22694653de6ce75430f4538` is represented at its native 320
dimensions in `backend/config/embedding_bakeoff.json`, the bakeoff report,
private run/provenance files, Dataset metadata, validation, and tests. No
1024-dimensional variant is asserted or fabricated.

## Canonical Dataset contents

The private Dataset preserves:

- the original 100-source, 1,400-pair blinded superset;
- the verified schema, source strata, manifest, snapshot manifest, and bakeoff
  report;
- all 13 run files and blind-ID-to-system mappings under `private/`;
- explicit checksum, provenance, upstream-rights, privacy, and no-real-label
  notes;
- weak/silver lexical and duplicate/version diagnostics, with unavailable task,
  lineage, and citation fields explicitly null;
- the local annotation, merge/adjudication, validation, and scoring code.

Titles and abstracts retain upstream rights. The private package is for
internal research evaluation and is not licensed for public redistribution.
Annotator IDs must be pseudonymous, and notes must not contain personal data,
credentials, production queries, or unpublished review material.

## First-pass tranche and workload

The first pass selects 20 sources, four from each document-length quintile, and
keeps every de-duplicated pooled candidate for those sources: 281 unique real
pairs. This preserves complete top-four judgment coverage for all 13 candidate
systems while reducing the initial source set by 80%.

The recommended two-annotator schedule uses 20% shared real assignments, 5%
hidden repeat items, and 2% synthetic cross-domain traps:

| Assignment | Real | Hidden repeats | Synthetic traps | Total |
| --- | ---: | ---: | ---: | ---: |
| Annotator 1 | 170 | 8 | 4 | 182 |
| Annotator 2 | 169 | 8 | 4 | 181 |

The two assignments contain 58 shared real pairs and cover all 281 unique real
pairs. At 35-45 seconds per item, budget 1.8-2.3 hours per annotator, or about
3.5-4.5 total annotation hours before adjudication.

Expand by another balanced 20 sources when weighted agreement is below 0.65,
unsure plus skip exceeds 10%, a leading paired 95% bootstrap interval includes
zero, a leading nDCG@4 interval is wider than 0.08, or any system has less than
90% judged top-four coverage. Continue only as needed through the preserved
100-source/1,400-pair ceiling.

## Human workflow

Exact launch sequence for annotator 1:

```bash
uv run --env-file backend/keys.env hf download \
  nielsr/paperswithcode-relevance-judgments --type dataset \
  --revision 924febd6a2de42f450cce9cc20fab9909aeadd32 \
  --local-dir /tmp/pwc-related-judgments
uv run --env-file backend/keys.env python \
  backend/scripts/related_papers_annotation.py verify-package \
  --root /tmp/pwc-related-judgments
uv run --env-file backend/keys.env python \
  backend/scripts/related_papers_annotation.py serve \
  --tranche /tmp/pwc-related-judgments/data/first_pass/blinded_pool.jsonl \
  --state-dir /tmp/pwc-related-annotation-state \
  --annotator-id ANNOTATOR_1 --annotator-index 0 --annotator-count 2 \
  --open-browser
```

The second annotator uses a distinct ID and `--annotator-index 1`. The local
browser shows only randomized source/candidate title and abstract text. Grades
are `0/1/2`, with optional unsure, skip, and notes. Progress is written
atomically and bound to an assignment fingerprint, so a state file cannot be
exported against a changed tranche.

After annotation, use `export` for each annotator, `merge`, the
`serve-adjudication` browser for disagreements, `export-adjudication`, and
`validate`. Keep `private/` hidden throughout. Scoring requires the literal
confirmation `--confirm UNBLIND_AND_SCORE` and consumes only the frozen,
validated adjudicated export.

QC reports hidden-repeat exact agreement, synthetic-trap accuracy,
cross-annotator weighted agreement, unsure rate, skip rate, and adjudication
count. Synthetic traps have an expected unrelated grade only for artificial
cross-domain text; they never assign or imply a label for a real pair.

## Deterministic scoring

The scorer produces source-level bootstrap 95% intervals for nDCG@4, graded
Precision@4, pooled Recall@20, duplicate rate, and top-4/top-20 judgment
coverage. Pairwise system comparisons use paired source bootstrap differences,
two-sided bootstrap p-values, and Holm correction across reported comparisons.
Unjudged top-four lists are excluded from quality means and remain visible as a
coverage loss. Recall@20 is explicitly recall within the judged pooled set, not
corpus-wide recall.

Silver diagnostics include lexical Jaccard and normalized-title duplicate or
version heuristics. The immutable snapshot does not carry task membership,
stored pairwise lineage, or citation edges, so those fields are null rather
than inferred. Silver signals cannot replace human judgments.

## Verification

- Hugging Face `datasets` loaded the 1,400-row superset and 281-row first pass.
- A live local HTTP smoke test loaded 182 randomized items and persisted an
  unsure action successfully.
- A synthetic-only round trip produced two exports, merged all 281 real pairs,
  adjudicated five induced disagreements, validated all 281 final synthetic
  grades, and generated results for all 13 systems with full top-four coverage.
- 14 targeted embedding/annotation tests passed.
- targeted Ruff checks passed.
- the final pinned Dataset download passed its checksum manifest; a repeat
  upload was a no-op at the same revision.

## Evidence required before a full-backfill goal

Do not authorize a full 104k backfill until all of the following exist:

1. Two independent human annotation exports for the first pass, frozen before
   unblinding, with QC rates and all disagreements adjudicated.
2. Acceptable agreement/QC: weighted agreement at least 0.65, hidden-repeat
   agreement and trap accuracy reported, and unsure/skip no more than 10%, or a
   documented reason plus another balanced tranche.
3. Per-system bootstrap intervals and paired comparisons showing a material
   gain over the existing task baseline and the keyword TF-IDF baseline; if
   leading intervals overlap or are too wide, expand in 20-source batches.
4. At least 200 human-judged sources before production activation, as required
   by `PLAN_RELATED_PAPERS.md`; the current 100-source superset is only the
   bakeoff stage.
5. A separately pinned offline query-vector evaluation of the 59 search queries
   covering MRR@10, nDCG@10, Recall@20, exact identity regressions, and hybrid
   versus FTS behavior. Document clustering judgments do not establish search
   quality.
6. If the 80M model remains competitive, one authorized corrected 320-D `l4x1`
   run for comparable throughput, peak VRAM, cost, and an `ef_search` sweep.
7. A selected model/dimension with recorded license, model revision, query and
   document contracts, measured full-corpus storage/index headroom, cost/time
   projection, rollback plan, and separate production migration/backfill
   authority.

Only this combined evidence can support the next goal. Sparse fixtures,
qualitative neighbors, silver diagnostics, or synthetic labels cannot select a
production winner.
