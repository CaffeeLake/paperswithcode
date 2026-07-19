-- Add the three editorial research-trend bullets shown below the Agents task
-- description.
UPDATE tasks
SET research_trends = jsonb_build_array(
    'Agents are moving from short, prompt-scripted reasoning loops toward terminal-based systems that operate in real software environments. [ReAct](/paper/2210.03629) established the interleaved reasoning-and-action pattern; [Terminal-Bench 2.1](/benchmark/terminal-bench-2-1?task=agents) now emphasizes difficult multi-step command-line work with executable verification, where planning, tool use, recovery, and robust harnesses matter as much as model knowledge.',
    'Long-horizon reasoning is becoming the central capability bottleneck. Widely reported benchmarks such as [BrowseComp](/benchmark/browsecomp?task=agents) and [Toolathlon](/benchmark/toolathlon?task=agents) reward persistent search and roughly 20-turn, multi-application workflows; their leading systems combine high reasoning effort with context compaction, code execution, programmatic tools, and multi-agent delegation to stay on task.',
    'Personal agents are becoming persistent, user-specific systems rather than disposable chat sessions. The [OpenClaw project](https://openclaw.ai/) popularized always-on assistants connected to local tools and messaging surfaces, while the [Hermes Agent project](https://hermes-agent.nousresearch.com/) combines one cross-surface memory with learned skills, scheduling, and isolated subagents; [Claw-Eval](/benchmark/claw-eval?task=agents) reflects the resulting focus on completion, safety, and robustness across real-world interactions.'
),
updated_at = NOW()
WHERE slug = 'agents';
