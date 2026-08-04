-- Add a first batch of major foundational methods that were missing from the
-- method taxonomy. Each method uses its introducing paper as the canonical
-- source and image credit.

INSERT INTO methods (
    slug, name, full_name, description, keywords,
    area_id, introduced_year, source_paper_id, source_url, source_title,
    code_snippet_url, image_url, image_credit
)
VALUES
(
    'masked-autoencoder',
    'Masked Autoencoder (MAE)',
    'Masked Autoencoder (MAE)',
    'A Masked Autoencoder (MAE) learns visual representations by hiding most image patches, encoding only the visible subset, and using a lightweight decoder to reconstruct the missing pixels. This asymmetric design makes self-supervised pre-training of large [Vision Transformers](/methods/vision-transformer) efficient and scalable.',
    'masked autoencoder, masked autoencoders, MAE, masked image modeling, MIM',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2021,
    (SELECT id FROM papers WHERE arxiv_id = '2111.06377' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Masked Autoencoders Are Scalable Vision Learners',
    NULL,
    NULL,
    '[Masked Autoencoders Are Scalable Vision Learners](/paper/2111.06377)'
),
(
    'graph-attention-network',
    'Graph Attention Network (GAT)',
    'Graph Attention Network (GAT)',
    'A Graph Attention Network (GAT) updates each node by attending over its neighbors and learning how much weight to assign to every connection. It brings masked self-attention to [Graph Neural Networks](/methods/graph-neural-network) without requiring spectral decompositions or a fixed graph structure.',
    'graph attention network, graph attention networks, GAT, GATs, graph attention layer',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2017,
    (SELECT id FROM papers WHERE arxiv_id = '1710.10903' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Graph Attention Networks',
    NULL,
    NULL,
    '[Graph Attention Networks](/paper/1710.10903)'
),
(
    'swiglu',
    'SwiGLU',
    'Swish-Gated Linear Unit (SwiGLU)',
    'SwiGLU is a gated activation used in [Transformer](/methods/transformer) feed-forward blocks. It multiplies a SiLU-activated linear projection by a second linear projection, giving the network a learnable gate that often improves quality over conventional ReLU or GELU feed-forward layers.',
    'SwiGLU, swish gated linear unit, swish-gated linear unit, GLU variant, gated linear unit',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2020,
    (SELECT id FROM papers WHERE arxiv_id = '2002.05202' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'GLU Variants Improve Transformer',
    NULL,
    NULL,
    '[GLU Variants Improve Transformer](/paper/2002.05202)'
),
(
    'neural-ode',
    'Neural ODE',
    'Neural Ordinary Differential Equation (Neural ODE)',
    'A Neural ODE defines hidden-state dynamics with a neural network and computes the output by solving an ordinary differential equation. This continuous-depth alternative to a discrete stack of layers supports adaptive computation and memory-efficient training through the adjoint method.',
    'neural ODE, neural ordinary differential equation, neural ordinary differential equations, ODE-Net, continuous-depth network, continuous normalizing flow',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2018,
    (SELECT id FROM papers WHERE arxiv_id = '1806.07366' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Neural Ordinary Differential Equations',
    NULL,
    NULL,
    '[Neural Ordinary Differential Equations](/paper/1806.07366)'
),
(
    'self-consistency',
    'Self-Consistency',
    'Self-Consistency Decoding',
    'Self-consistency improves [Chain-of-Thought prompting](/methods/chain-of-thought-cot) by sampling multiple diverse reasoning paths and selecting the answer on which they agree. It replaces a single greedy reasoning trace with a simple test-time aggregation strategy.',
    'self-consistency, self consistency, self-consistency decoding, chain-of-thought self-consistency, CoT-SC, majority vote reasoning',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2022,
    (SELECT id FROM papers WHERE arxiv_id = '2203.11171' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Self-Consistency Improves Chain of Thought Reasoning in Language Models',
    NULL,
    NULL,
    '[Self-Consistency Improves Chain of Thought Reasoning in Language Models](/paper/2203.11171)'
),
(
    'prompt-tuning',
    'Prompt Tuning',
    'Prompt Tuning',
    'Prompt tuning adapts a frozen language model by learning a small sequence of continuous soft-prompt embeddings that is prepended to the input. It is a [parameter-efficient fine-tuning](/methods/peft) method that stores only a tiny task-specific prompt instead of a full model copy.',
    'prompt tuning, soft prompt tuning, soft prompts, continuous prompts, learned prompts, parameter-efficient prompt tuning',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2021,
    (SELECT id FROM papers WHERE arxiv_id = '2104.08691' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'The Power of Scale for Parameter-Efficient Prompt Tuning',
    NULL,
    NULL,
    '[The Power of Scale for Parameter-Efficient Prompt Tuning](/paper/2104.08691)'
),
(
    'prefix-tuning',
    'Prefix Tuning',
    'Prefix Tuning',
    'Prefix tuning keeps a pre-trained language model frozen and learns a small continuous prefix whose virtual tokens are available to attention layers during generation. The learned prefix provides a modular, [parameter-efficient](/methods/peft) set of task-specific parameters.',
    'prefix tuning, prefix-tuning, continuous prefix, virtual tokens, learned prefix, parameter-efficient fine-tuning',
    (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
    2021,
    (SELECT id FROM papers WHERE arxiv_id = '2101.00190' ORDER BY is_latest_version DESC, id DESC LIMIT 1),
    NULL,
    'Prefix-Tuning: Optimizing Continuous Prompts for Generation',
    NULL,
    NULL,
    '[Prefix-Tuning: Optimizing Continuous Prompts for Generation](/paper/2101.00190)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT m.source_paper_id, m.id
FROM methods m
WHERE m.slug IN (
    'masked-autoencoder',
    'graph-attention-network',
    'swiglu',
    'neural-ode',
    'self-consistency',
    'prompt-tuning',
    'prefix-tuning'
)
  AND m.source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
