-- Add the three editorial research-trend bullets shown below the Robotics task
-- description.
UPDATE tasks
SET research_trends = jsonb_build_array(
    '**Foundation policies replace task-specific stacks.** Robotics is shifting from separately trained perception, planning, and control modules toward vision-language-action models that turn observations, instructions, and robot states directly into transferable actions. [RT-2](/paper/2307.15818) established web-to-robot semantic transfer, [OpenVLA](/paper/2406.09246) made the recipe open and fine-tunable, and [π0](/paper/2410.24164) extends it with flow-matched continuous action generation across multiple embodiments.',
    '**World modeling moves into the control loop.** Recent systems are learning physical dynamics alongside actions so policies can anticipate long-horizon consequences, while avoiding the latency of generating full futures at every step. [Causal World Modeling](/paper/2601.21998) uses joint latent video-action prediction and closed-loop feedback, [WLA](/paper/2606.05979) unifies subtask, subgoal-image, and action prediction, and [Fast-WAM](/paper/2603.16666) shows video co-training can preserve gains while skipping test-time imagination.',
    '**Scale comes from diverse data and reproducible stress tests.** Gains increasingly depend on broad real-world demonstrations, synthetic task generation, domain randomization, and sim-real validation—not only larger backbones. [DROID](/paper/2403.12945) widened collection across environments and institutions, [RoboTwin 2.0](/paper/2506.18088) automates randomized bimanual data, and the widely reported [LIBERO](/benchmark/libero?task=robotics) and [SimplerEnv](/benchmark/simplerenv-widowx?task=robotics) leaderboards emphasize cross-task transfer, distribution shifts, and reproducible real-to-sim evaluation.'
),
updated_at = NOW()
WHERE slug = 'robotics';
