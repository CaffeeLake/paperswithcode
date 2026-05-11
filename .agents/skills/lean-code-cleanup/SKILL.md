---
name: lean-code-cleanup
description: Find and remove code that makes a codebase larger or harder to maintain without adding value. Use this skill whenever the user asks to clean up code, make code leaner or more concise, reduce bloat, remove unused or obsolete code, simplify overbuilt implementations, prune stale compatibility paths, or run a regular cleanup pass across a repo or folder. Trigger even if the user phrases it casually, such as "tidy this up", "trim dead code", "make this less bloated", or "look for stuff we can delete".
---

# Lean Code Cleanup

This skill helps make a codebase smaller, clearer, and easier to change. The goal is not to chase clever minimalism; it is to remove code whose purpose is gone, duplicated, speculative, unreachable, or much more complex than the current product needs.

## Cleanup Philosophy

Prefer boring, evidence-backed reductions:

- Delete code only when you can explain why it is unused, obsolete, duplicated, or safely replaceable.
- Simplify code when the simpler version preserves behavior and matches the local style.
- Keep public contracts, persisted data, migrations, operational scripts, and compatibility paths unless the user has made it clear they no longer matter.
- Avoid broad rewrites during cleanup passes. A small clean diff is better than a heroic refactor that mixes risk with deletion.
- Treat untracked generated files, logs, caches, and local outputs differently from source code. They may be local noise rather than committed bloat.

## First Pass

Start by understanding the target scope:

1. Identify the folder, package, feature area, or file set the user wants cleaned.
2. Check the git working tree before edits. If files are already modified, assume those changes belong to the user and work around them.
3. Map the main entry points and ownership boundaries before deciding code is dead.
4. Separate candidates into:
   - **Source cleanup**: unused functions, duplicate wrappers, obsolete branches, stale examples, uncalled helpers.
   - **Generated/local noise**: logs, outputs, caches, build artifacts, pycache, vendored dumps.
   - **Risky historical code**: migrations, one-off database scripts, public API compatibility, data import tools.

For broad repo exploration, use a read-only exploration subagent when available. Ask it for evidence, not just opinions.

## Evidence Checklist

Before deleting code, gather at least two relevant signals when practical:

- Exact reference search for the symbol, route, script name, or file path.
- Import graph or entry-point check.
- Tests or docs that cover the replacement path.
- Runtime registration check, such as router inclusion, CLI command registration, cron workflow references, package exports, or config references.
- Git tracking check for artifacts that look generated.
- Linter or dead-code detector output, treated as a hint rather than proof.

If evidence is mixed, keep the code and report it as a candidate instead of deleting it.

## What To Clean Up

Good regular-cleanup targets:

- Unused imports, variables, helper parameters, and private functions.
- Duplicate wrappers that call a richer canonical path with fewer options.
- Stale example scripts that are not referenced by docs, tests, CI, or workflows.
- Old compatibility code for unshipped branch work.
- Repeated inline logic that already has a local helper.
- Comments that narrate obvious code or document behavior that no longer exists.
- Defensive fallback branches that cannot happen under current invariants.
- Generated files that are accidentally tracked, after confirming they are not intentional fixtures.

Be cautious with:

- Database migrations and data repair scripts.
- Public API endpoints and response fields.
- CLI scripts called by cron, deployment, or docs.
- Test fixtures and snapshots.
- Legacy data importers when the repo still documents them.
- Backwards compatibility for shipped behavior.

## Editing Workflow

Use this order:

1. Make a short candidate list with evidence and risk level.
2. Pick the lowest-risk candidates first.
3. Edit narrowly. Prefer deleting a whole unused file, function, endpoint wrapper, or parameter over reshaping unrelated code.
4. Preserve user changes in dirty files. If cleanup touches an already-modified file, inspect the diff first and edit only around the target.
5. After edits, search for deleted symbols and paths again.
6. Run the cheapest meaningful checks:
   - Linter for edited files.
   - Compile/typecheck for edited language when available.
   - Focused tests for affected behavior.
7. If a relevant test tool is missing, say so and include the checks that did run.

## Reporting Back

Keep the report concise and action-oriented:

- State what was removed or simplified.
- Mention anything intentionally left alone because it was too risky or still referenced.
- List verification commands and results.
- If further cleanup remains, give a short candidate list with risk levels.

Do not create standalone summary markdown files unless the user explicitly asks for documentation.

## Regular Cleanup Cadence

When the user says they want to run this regularly, default to a conservative maintenance pass:

1. Scan for newly introduced local/generated clutter.
2. Check for obvious unused code in the requested area.
3. Remove only low-risk items.
4. Leave a concise note of higher-risk candidates for a later, explicit cleanup pass.

This keeps routine cleanup cheap and prevents it from becoming a surprise refactor.
