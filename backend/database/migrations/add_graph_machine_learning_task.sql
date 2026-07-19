-- Curated Graph Machine Learning task family.
--
-- The top-level task is intentionally broad, while the child tasks are the
-- user-facing leaderboards users expect when browsing graph ML papers.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Graph Machine Learning',
    'graph-machine-learning',
    'Graph Machine Learning studies models for data represented as nodes, edges, and attributes, including citation networks, molecules, knowledge graphs, recommender graphs, temporal interaction networks, and large heterogeneous graphs. It covers node-, edge-, link-, and graph-level prediction, and connects to [Biology](/tasks/biology), [Tabular Learning](/tasks/tabular-learning), and [Retrieval](/tasks/retrieval).',
    'graph machine learning, graph ML, graph neural network, graph neural networks, GNN, GNNs, graph representation learning, graph foundation model, message passing neural network, MPNN, graph transformer, graph attention network, graph convolutional network',
    (SELECT id FROM areas WHERE name = 'Other' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    'Generated concept image',
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

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id, is_visible
)
VALUES
(
    'Node Classification',
    'node-classification',
    'Node Classification predicts categorical labels for nodes in a graph from node attributes, graph structure, and optionally edge attributes. Common settings include semi-supervised transductive citation-network classification, inductive classification on large attributed graphs, heterophilous node classification, and node property prediction in benchmark suites such as OGB.',
    'node classification, semi-supervised node classification, transductive node classification, inductive node classification, heterophilous node classification, heterophily, homophily, citation network classification, node property prediction',
    (SELECT area_id FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    true
),
(
    'Graph Classification',
    'graph-classification',
    'Graph Classification assigns labels to entire graphs, such as molecules, proteins, superpixel graphs, social ego-networks, or program graphs. It covers graph-level classification benchmarks, graph pooling methods, graph isomorphism networks, and graph transformers evaluated on whole-graph prediction.',
    'graph classification, graph-level classification, molecular graph classification, social graph classification, graph isomorphism network, graph pooling',
    (SELECT area_id FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    true
),
(
    'Link Prediction',
    'link-prediction',
    'Link Prediction estimates missing or future edges between nodes in a graph. It includes static edge prediction, graph completion, citation recommendation, drug interaction prediction, temporal link prediction, and related graph completion setups.',
    'link prediction, edge prediction, link property prediction, graph completion, network completion, knowledge graph completion, temporal link prediction',
    (SELECT area_id FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    true
),
(
    'Graph Regression',
    'graph-regression',
    'Graph Regression predicts continuous graph-level properties, especially molecular, chemical, and structural properties. Standard benchmarks include ZINC-style molecular property regression, QM9 quantum chemistry targets, PCQM-style molecular tasks, and structural graph regression suites.',
    'graph regression, graph property regression, molecular property regression, ZINC, PCQM4M, QM9, peptide structure prediction',
    (SELECT area_id FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    true
),
(
    'Molecular Property Prediction',
    'molecular-property-prediction',
    'Molecular Property Prediction uses molecular graphs and learned representations to classify or regress chemical, toxicity, pharmacokinetic, and quantum-chemistry properties. It is a core Graph Machine Learning subtask and is closely related to [Biology](/tasks/biology).',
    'molecular property prediction, molecule property prediction, molecular graph, molecule graph, MoleculeNet, ADMET, molecular representation learning, graph chemistry',
    (SELECT area_id FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    true
),
(
    'Knowledge Graph Completion',
    'knowledge-graph-completion',
    'Knowledge Graph Completion predicts missing entities, relations, or triples in multi-relational knowledge graphs. It covers knowledge graph embeddings, entity prediction, relation prediction, inductive completion, temporal knowledge graphs, and complex query answering setups.',
    'knowledge graph completion, knowledge graph embedding, KGE, entity prediction, relation prediction, triple classification, complex query answering, inductive knowledge graph completion',
    (SELECT area_id FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    true
),
(
    'Temporal Graph Learning',
    'temporal-graph-learning',
    'Temporal Graph Learning models graphs whose nodes, edges, attributes, or relation types evolve over time. It includes dynamic link prediction, future node property prediction, temporal knowledge graph forecasting, and heterogeneous temporal graph benchmarks such as TGB.',
    'temporal graph learning, dynamic graph learning, temporal link prediction, dynamic node classification, temporal knowledge graph, TGB, temporal graph benchmark',
    (SELECT area_id FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'graph-machine-learning' LIMIT 1),
    true
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    is_visible = EXCLUDED.is_visible,
    updated_at = CURRENT_TIMESTAMP;

-- Graph ML is a hub task; show high-signal adjacent task families when present.
INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, v.ord
FROM tasks t
CROSS JOIN (VALUES
    ('biology', 0),
    ('tabular-learning', 1),
    ('retrieval', 2)
) AS v(slug, ord)
JOIN tasks s ON s.slug = v.slug
WHERE t.slug = 'graph-machine-learning'
ON CONFLICT DO NOTHING;

-- Molecular graph work should be discoverable from the Biology task too.
INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, 0
FROM tasks t
JOIN tasks s ON s.slug = 'biology'
WHERE t.slug = 'molecular-property-prediction'
ON CONFLICT DO NOTHING;

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, 0
FROM tasks t
JOIN tasks s ON s.slug = 'molecular-property-prediction'
WHERE t.slug = 'biology'
ON CONFLICT DO NOTHING;
