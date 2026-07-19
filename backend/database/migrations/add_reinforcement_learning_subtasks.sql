INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Reinforcement Learning',
    'reinforcement-learning',
    'Reinforcement Learning studies agents that learn to act through interaction with environments, optimizing long-term reward from feedback. It covers value-based methods, policy gradients, actor-critic methods, model-based and model-free learning, offline RL, multi-agent RL, exploration, continuous control, game playing, and generalization across environment distributions. It connects to [Robotics](/tasks/robotics), [World Models](/tasks/world-models), and [Agents](/tasks/agents), while this page focuses on core RL benchmark suites.',
    'reinforcement learning, RL, deep reinforcement learning, online RL, offline RL, value-based RL, Q-learning, deep Q-network, DQN, policy gradient, actor-critic, model-free RL, model-based RL, continuous control, Atari, Arcade Learning Environment, Procgen, D4RL, SMAC, multi-agent RL, exploration, sparse reward, imitation learning, temporal difference learning',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    'Generated locally for the Reinforcement Learning task',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    is_visible = EXCLUDED.is_visible,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;

WITH parent AS (
    SELECT id, area_id, level FROM tasks WHERE slug = 'reinforcement-learning'
),
subtasks(name, slug, description, keywords) AS (
    VALUES
    (
        'Atari Games',
        'atari-games',
        'Atari Games benchmarks evaluate reinforcement learning agents on Atari 2600 video games through the Arcade Learning Environment and related protocols such as Atari 57 and Atari 100k. They are central tests for value-based learning, exploration, sample efficiency, and general game-playing ability.',
        'Atari, Atari 2600, Atari games, Arcade Learning Environment, Atari 57, Atari 100k, human normalized score, game score, Montezuma''s Revenge'
    ),
    (
        'Continuous Control',
        'continuous-control',
        'Continuous Control benchmarks evaluate agents in environments with continuous action spaces, including locomotion, balancing, manipulation, and physics-control tasks from MuJoCo, Gymnasium, and the DeepMind Control Suite.',
        'continuous control, MuJoCo, DeepMind Control Suite, dm_control, DMC, Gym, Gymnasium, robot locomotion, locomotion, HalfCheetah, Hopper, Walker2d, Ant, Humanoid, control suite'
    ),
    (
        'Offline Reinforcement Learning',
        'offline-reinforcement-learning',
        'Offline Reinforcement Learning trains policies from fixed datasets without further online environment interaction. Benchmarks such as D4RL measure whether agents can learn robust policies from logged data produced by random, medium, expert, replay, or mixed-quality behavior policies.',
        'offline reinforcement learning, offline RL, batch RL, data-driven RL, D4RL, offline control, conservative Q-learning, CQL, implicit Q-learning, IQL, behavior cloning, dataset policy'
    ),
    (
        'Multi-Agent Reinforcement Learning',
        'multi-agent-reinforcement-learning',
        'Multi-Agent Reinforcement Learning studies multiple interacting agents that learn coordinated or competitive behavior. Cooperative benchmarks such as SMAC test centralized-training/decentralized-execution methods, value factorization, communication, and credit assignment.',
        'multi-agent reinforcement learning, multi-agent RL, MARL, cooperative multi-agent RL, SMAC, SMACv2, SMAC+, StarCraft Multi-Agent Challenge, QMIX, QPLEX, MAPPO, decentralized execution, centralized training'
    ),
    (
        'Procedural Generalization',
        'procedural-generalization',
        'Procedural Generalization benchmarks evaluate how reinforcement learning agents transfer across procedurally generated levels, tasks, or environment instances rather than memorizing a fixed training set. Procgen, Obstacle Tower, MiniGrid, and BabyAI-style tasks stress sample efficiency and robust generalization.',
        'procedural generalization, procedural generation, Procgen, ProcGen, Obstacle Tower, MiniGrid, BabyAI, RL generalization, train levels, test levels, sample efficiency'
    )
)
INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id, is_visible
)
SELECT
    s.name,
    s.slug,
    s.description,
    s.keywords,
    parent.area_id,
    parent.level + 1,
    parent.id,
    true
FROM subtasks s
CROSS JOIN parent
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    is_visible = EXCLUDED.is_visible,
    updated_at = CURRENT_TIMESTAMP;
