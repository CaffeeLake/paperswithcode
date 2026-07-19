"""Declarative graph-ML benchmark specifications."""

from typing import Any


def ogb_dataset(
    name: str,
    slug: str,
    task_slug: str,
    metric: str,
    short_description: str,
    description: str,
    homepage: str,
) -> dict[str, Any]:
    return {
        "name": name,
        "slug": slug,
        "full_name": name,
        "short_description": short_description,
        "description": description,
        "homepage": homepage,
        "url": homepage,
        "source_key": "ogb",
        "introduced_year": 2020,
        "task_metrics": [(task_slug, metric)],
    }


BENCHMARKS: list[dict[str, Any]] = [
    # Batch A: OGB node property prediction.
    ogb_dataset(
        "ogbn-arxiv",
        "ogbn-arxiv",
        "node-classification",
        "Accuracy",
        "OGB citation-network node classification benchmark.",
        "ogbn-arxiv is an Open Graph Benchmark node property prediction dataset "
        "built from the Microsoft Academic Graph arXiv citation network. The "
        "task predicts each paper's subject area from graph structure and text "
        "features.",
        "https://ogb.stanford.edu/docs/nodeprop/#ogbn-arxiv",
    ),
    ogb_dataset(
        "ogbn-products",
        "ogbn-products",
        "node-classification",
        "Accuracy",
        "Large-scale product co-purchasing node classification benchmark.",
        "ogbn-products is an OGB node property prediction benchmark over an "
        "Amazon product co-purchasing graph. Nodes are products and labels are "
        "product categories.",
        "https://ogb.stanford.edu/docs/nodeprop/#ogbn-products",
    ),
    ogb_dataset(
        "ogbn-proteins",
        "ogbn-proteins",
        "node-classification",
        "ROC-AUC",
        "Protein function prediction benchmark from OGB.",
        "ogbn-proteins is an OGB multi-label node property prediction dataset "
        "over a protein-protein association graph. The leaderboard tracks "
        "protein function prediction with ROC-AUC.",
        "https://ogb.stanford.edu/docs/nodeprop/#ogbn-proteins",
    ),
    ogb_dataset(
        "ogbn-mag",
        "ogbn-mag",
        "node-classification",
        "Accuracy",
        "Heterogeneous academic graph node classification benchmark.",
        "ogbn-mag is an OGB heterogeneous node property prediction dataset "
        "derived from Microsoft Academic Graph. The task predicts paper venues "
        "from author, institution, field, and citation relations.",
        "https://ogb.stanford.edu/docs/nodeprop/#ogbn-mag",
    ),
    ogb_dataset(
        "ogbn-papers100M",
        "ogbn-papers100m",
        "node-classification",
        "Accuracy",
        "Very large citation-network node classification benchmark.",
        "ogbn-papers100M is a massive OGB node property prediction benchmark "
        "with over 100 million paper nodes. The task predicts paper subject "
        "areas at web-scale graph-learning size.",
        "https://ogb.stanford.edu/docs/nodeprop/#ogbn-papers100M",
    ),
    # Batch A: OGB link property prediction.
    ogb_dataset(
        "ogbl-collab",
        "ogbl-collab",
        "link-prediction",
        "Hits@50",
        "Collaboration graph link prediction benchmark from OGB.",
        "ogbl-collab is an OGB collaboration graph benchmark where methods "
        "predict future co-authorship links. The leaderboard uses Hits@50.",
        "https://ogb.stanford.edu/docs/linkprop/#ogbl-collab",
    ),
    ogb_dataset(
        "ogbl-citation2",
        "ogbl-citation2",
        "link-prediction",
        "MRR",
        "Citation recommendation link prediction benchmark from OGB.",
        "ogbl-citation2 is an OGB citation graph benchmark for predicting "
        "directed citation links. The leaderboard uses mean reciprocal rank.",
        "https://ogb.stanford.edu/docs/linkprop/#ogbl-citation2",
    ),
    ogb_dataset(
        "ogbl-ddi",
        "ogbl-ddi",
        "link-prediction",
        "Hits@20",
        "Drug-drug interaction link prediction benchmark from OGB.",
        "ogbl-ddi is an OGB benchmark for predicting drug-drug interaction "
        "links in a homogeneous drug graph. The leaderboard uses Hits@20.",
        "https://ogb.stanford.edu/docs/linkprop/#ogbl-ddi",
    ),
    ogb_dataset(
        "ogbl-ppa",
        "ogbl-ppa",
        "link-prediction",
        "Hits@100",
        "Protein association link prediction benchmark from OGB.",
        "ogbl-ppa is an OGB protein association graph benchmark. The task "
        "predicts links between proteins and reports Hits@100.",
        "https://ogb.stanford.edu/docs/linkprop/#ogbl-ppa",
    ),
    {
        **ogb_dataset(
            "ogbl-wikikg2",
            "ogbl-wikikg2",
            "link-prediction",
            "MRR",
            "Wikidata knowledge graph completion benchmark from OGB.",
            "ogbl-wikikg2 is an OGB link property prediction dataset derived "
            "from Wikidata. It is used for knowledge graph completion with MRR.",
            "https://ogb.stanford.edu/docs/linkprop/#ogbl-wikikg2",
        ),
        "task_metrics": [
            ("link-prediction", "MRR"),
            ("knowledge-graph-completion", "MRR"),
        ],
    },
    {
        **ogb_dataset(
            "ogbl-biokg",
            "ogbl-biokg",
            "link-prediction",
            "MRR",
            "Biomedical knowledge graph completion benchmark from OGB.",
            "ogbl-biokg is an OGB biomedical knowledge graph benchmark for "
            "predicting missing typed biological relations. The leaderboard "
            "uses MRR.",
            "https://ogb.stanford.edu/docs/linkprop/#ogbl-biokg",
        ),
        "task_metrics": [
            ("link-prediction", "MRR"),
            ("knowledge-graph-completion", "MRR"),
        ],
    },
    # Batch A: OGB graph property prediction.
    ogb_dataset(
        "ogbg-molhiv",
        "ogbg-molhiv",
        "molecular-property-prediction",
        "ROC-AUC",
        "Molecular HIV activity prediction benchmark from OGB.",
        "ogbg-molhiv is an OGB molecular graph property prediction benchmark "
        "for classifying HIV inhibition activity. The leaderboard uses ROC-AUC.",
        "https://ogb.stanford.edu/docs/graphprop/#ogbg-mol",
    ),
    ogb_dataset(
        "ogbg-molpcba",
        "ogbg-molpcba",
        "molecular-property-prediction",
        "AP",
        "Large-scale molecular activity prediction benchmark from OGB.",
        "ogbg-molpcba is an OGB multi-task molecular graph classification "
        "benchmark based on PubChem BioAssay labels. The leaderboard uses "
        "average precision.",
        "https://ogb.stanford.edu/docs/graphprop/#ogbg-mol",
    ),
    ogb_dataset(
        "ogbg-ppa",
        "ogbg-ppa",
        "graph-classification",
        "Accuracy",
        "Protein association graph classification benchmark from OGB.",
        "ogbg-ppa is an OGB graph property prediction benchmark where each "
        "graph represents a protein association neighborhood and the task is "
        "graph-level taxonomy classification.",
        "https://ogb.stanford.edu/docs/graphprop/#ogbg-ppa",
    ),
    ogb_dataset(
        "ogbg-code2",
        "ogbg-code2",
        "graph-classification",
        "F1",
        "Program graph property prediction benchmark from OGB.",
        "ogbg-code2 is an OGB graph property prediction benchmark built from "
        "Python abstract syntax trees. The task predicts method names from "
        "program structure and reports F1.",
        "https://ogb.stanford.edu/docs/graphprop/#ogbg-code2",
    ),
    # Batch B: classic citation and heterophily node classification.
    {
        "name": "Cora (fixed 20 nodes per class)",
        "slug": "cora-fixed-20-nodes-per-class",
        "full_name": "Cora fixed 20 nodes per class",
        "short_description": "Planetoid-style Cora node classification split.",
        "description": "Cora fixed 20 nodes per class is the classic "
        "Planetoid-style semi-supervised node classification protocol for the "
        "Cora citation network.",
        "homepage": "https://github.com/kimiyoung/planetoid",
        "url": "https://github.com/kimiyoung/planetoid",
        "source_key": "planetoid",
        "introduced_year": 2016,
        "task_metrics": [("node-classification", "Accuracy")],
    },
    {
        "name": "CiteSeer (fixed 20 nodes per class)",
        "slug": "citeseer-fixed-20-nodes-per-class",
        "full_name": "CiteSeer fixed 20 nodes per class",
        "short_description": "Planetoid-style CiteSeer node classification split.",
        "description": "CiteSeer fixed 20 nodes per class is the classic "
        "Planetoid-style semi-supervised node classification protocol for the "
        "CiteSeer citation network.",
        "homepage": "https://github.com/kimiyoung/planetoid",
        "url": "https://github.com/kimiyoung/planetoid",
        "source_key": "planetoid",
        "introduced_year": 2016,
        "task_metrics": [("node-classification", "Accuracy")],
    },
    {
        "name": "PubMed (fixed 20 nodes per class)",
        "slug": "pubmed-node-classification-fixed-20-nodes-per-class",
        "full_name": "PubMed fixed 20 nodes per class",
        "short_description": "Planetoid-style PubMed node classification split.",
        "description": "PubMed fixed 20 nodes per class is the graph-specific "
        "Planetoid-style citation-network node classification protocol. Its "
        "slug is graph-specific to avoid the unrelated PubMed summarization row.",
        "homepage": "https://github.com/kimiyoung/planetoid",
        "url": "https://github.com/kimiyoung/planetoid",
        "source_key": "planetoid",
        "introduced_year": 2016,
        "task_metrics": [("node-classification", "Accuracy")],
    },
    {
        "name": "Cora (60/20/20 random splits)",
        "slug": "cora-60-20-20-random-splits",
        "full_name": "Cora 60/20/20 random splits",
        "short_description": "Cora node classification with random 60/20/20 splits.",
        "description": "Cora 60/20/20 random splits tracks the random-split "
        "citation-network protocol used in heterophily and node-classification "
        "comparisons.",
        "homepage": "https://arxiv.org/abs/2210.07606",
        "url": "https://arxiv.org/abs/2210.07606",
        "source_key": "revisiting-heterophily",
        "introduced_year": 2022,
        "task_metrics": [("node-classification", "Accuracy")],
    },
    {
        "name": "CiteSeer (60/20/20 random splits)",
        "slug": "citeseer-60-20-20-random-splits",
        "full_name": "CiteSeer 60/20/20 random splits",
        "short_description": "CiteSeer node classification with random 60/20/20 splits.",
        "description": "CiteSeer 60/20/20 random splits tracks the random-split "
        "citation-network protocol used in heterophily and node-classification "
        "comparisons.",
        "homepage": "https://arxiv.org/abs/2210.07606",
        "url": "https://arxiv.org/abs/2210.07606",
        "source_key": "revisiting-heterophily",
        "introduced_year": 2022,
        "task_metrics": [("node-classification", "Accuracy")],
    },
    {
        "name": "Chameleon",
        "slug": "chameleon-node-classification",
        "full_name": "Chameleon node classification",
        "short_description": "Wikipedia-network heterophily node classification benchmark.",
        "description": "Chameleon is a heterophilous Wikipedia page network "
        "benchmark for node classification, commonly evaluated with random or "
        "Geom-GCN-style splits.",
        "homepage": "https://arxiv.org/abs/2002.05287",
        "url": "https://arxiv.org/abs/2002.05287",
        "source_key": "geom-gcn",
        "introduced_year": 2020,
        "task_metrics": [("node-classification", "Accuracy")],
    },
    {
        "name": "Squirrel",
        "slug": "squirrel-node-classification",
        "full_name": "Squirrel node classification",
        "short_description": "Wikipedia-network heterophily node classification benchmark.",
        "description": "Squirrel is a heterophilous Wikipedia page network "
        "benchmark for node classification, commonly used to evaluate graph "
        "learning under low homophily.",
        "homepage": "https://arxiv.org/abs/2002.05287",
        "url": "https://arxiv.org/abs/2002.05287",
        "source_key": "geom-gcn",
        "introduced_year": 2020,
        "task_metrics": [("node-classification", "Accuracy")],
    },
    {
        "name": "Actor",
        "slug": "actor-node-classification",
        "full_name": "Actor node classification",
        "short_description": "Film actor heterophily node classification benchmark.",
        "description": "Actor is a heterophilous actor co-occurrence graph "
        "benchmark for node classification, often used with Geom-GCN-style "
        "splits.",
        "homepage": "https://arxiv.org/abs/2002.05287",
        "url": "https://arxiv.org/abs/2002.05287",
        "source_key": "geom-gcn",
        "introduced_year": 2020,
        "task_metrics": [("node-classification", "Accuracy")],
    },
    {
        "name": "Roman-empire",
        "slug": "roman-empire",
        "full_name": "Roman-empire node classification",
        "short_description": "Modern heterophily node classification benchmark.",
        "description": "Roman-empire is a modern heterophilous node classification "
        "benchmark based on an English Wikipedia article graph.",
        "homepage": "https://arxiv.org/abs/2302.11640",
        "url": "https://arxiv.org/abs/2302.11640",
        "source_key": "critical-heterophily",
        "introduced_year": 2023,
        "task_metrics": [("node-classification", "Accuracy")],
    },
    {
        "name": "Tolokers",
        "slug": "tolokers",
        "full_name": "Tolokers node classification",
        "short_description": "Modern heterophily node classification benchmark.",
        "description": "Tolokers is a modern heterophilous node classification "
        "benchmark derived from a crowdsourcing platform interaction graph.",
        "homepage": "https://arxiv.org/abs/2302.11640",
        "url": "https://arxiv.org/abs/2302.11640",
        "source_key": "critical-heterophily",
        "introduced_year": 2023,
        "task_metrics": [("node-classification", "Accuracy")],
    },
    # Batch C: Benchmarking GNNs.
    {
        "name": "ZINC",
        "slug": "zinc",
        "full_name": "ZINC molecular graph regression",
        "short_description": "Molecular graph regression benchmark from Benchmarking GNNs.",
        "description": "ZINC is the molecular graph regression benchmark used in "
        "Benchmarking Graph Neural Networks. The task predicts constrained "
        "solubility and is evaluated with MAE.",
        "homepage": "https://github.com/graphdeeplearning/benchmarking-gnns",
        "url": "https://github.com/graphdeeplearning/benchmarking-gnns",
        "source_key": "benchmarking-gnns",
        "introduced_year": 2020,
        "task_metrics": [("graph-regression", "MAE")],
    },
    {
        "name": "PATTERN",
        "slug": "pattern",
        "full_name": "PATTERN node classification",
        "short_description": "Synthetic SBM node classification benchmark.",
        "description": "PATTERN is a synthetic stochastic block model node "
        "classification benchmark from Benchmarking Graph Neural Networks.",
        "homepage": "https://github.com/graphdeeplearning/benchmarking-gnns",
        "url": "https://github.com/graphdeeplearning/benchmarking-gnns",
        "source_key": "benchmarking-gnns",
        "introduced_year": 2020,
        "task_metrics": [("node-classification", "Accuracy")],
    },
    {
        "name": "CLUSTER",
        "slug": "cluster",
        "full_name": "CLUSTER node classification",
        "short_description": "Synthetic SBM clustering/node classification benchmark.",
        "description": "CLUSTER is a stochastic block model node classification "
        "benchmark from Benchmarking Graph Neural Networks.",
        "homepage": "https://github.com/graphdeeplearning/benchmarking-gnns",
        "url": "https://github.com/graphdeeplearning/benchmarking-gnns",
        "source_key": "benchmarking-gnns",
        "introduced_year": 2020,
        "task_metrics": [("node-classification", "Accuracy")],
    },
    {
        "name": "MNIST Superpixels",
        "slug": "mnist-superpixels",
        "full_name": "MNIST Superpixels graph classification",
        "short_description": "MNIST image classification converted to superpixel graphs.",
        "description": "MNIST Superpixels converts MNIST images into graph "
        "classification samples where nodes are superpixels and edges encode "
        "spatial neighborhood structure.",
        "homepage": "https://github.com/graphdeeplearning/benchmarking-gnns",
        "url": "https://github.com/graphdeeplearning/benchmarking-gnns",
        "source_key": "benchmarking-gnns",
        "introduced_year": 2020,
        "task_metrics": [("graph-classification", "Accuracy")],
    },
    {
        "name": "CIFAR10 Superpixels",
        "slug": "cifar10-superpixels",
        "full_name": "CIFAR10 Superpixels graph classification",
        "short_description": "CIFAR10 image classification converted to superpixel graphs.",
        "description": "CIFAR10 Superpixels converts CIFAR10 images into graph "
        "classification samples where nodes are superpixels and edges encode "
        "spatial neighborhood structure.",
        "homepage": "https://github.com/graphdeeplearning/benchmarking-gnns",
        "url": "https://github.com/graphdeeplearning/benchmarking-gnns",
        "source_key": "benchmarking-gnns",
        "introduced_year": 2020,
        "task_metrics": [("graph-classification", "Accuracy")],
    },
    # Batch C: LRGB.
    {
        "name": "Peptides-func",
        "slug": "peptides-func",
        "full_name": "Peptides-func graph classification",
        "short_description": "LRGB peptide function graph classification benchmark.",
        "description": "Peptides-func is a Long Range Graph Benchmark multi-label "
        "graph classification dataset for peptide function prediction. The "
        "leaderboard uses average precision.",
        "homepage": "https://github.com/vijaydwivedi75/lrgb",
        "url": "https://github.com/vijaydwivedi75/lrgb",
        "source_key": "lrgb",
        "introduced_year": 2022,
        "task_metrics": [("graph-classification", "AP")],
    },
    {
        "name": "Peptides-struct",
        "slug": "peptides-struct",
        "full_name": "Peptides-struct graph regression",
        "short_description": "LRGB peptide structure graph regression benchmark.",
        "description": "Peptides-struct is a Long Range Graph Benchmark graph "
        "regression dataset for predicting aggregate 3D structural properties "
        "of peptide molecules. The leaderboard uses MAE.",
        "homepage": "https://github.com/vijaydwivedi75/lrgb",
        "url": "https://github.com/vijaydwivedi75/lrgb",
        "source_key": "lrgb",
        "introduced_year": 2022,
        "task_metrics": [("graph-regression", "MAE")],
    },
    {
        "name": "PascalVOC-SP",
        "slug": "pascalvoc-sp",
        "full_name": "PascalVOC-SP node classification",
        "short_description": "LRGB superpixel node classification benchmark.",
        "description": "PascalVOC-SP is a Long Range Graph Benchmark node "
        "classification dataset built from Pascal VOC superpixel graphs. The "
        "leaderboard uses macro weighted F1.",
        "homepage": "https://github.com/vijaydwivedi75/lrgb",
        "url": "https://github.com/vijaydwivedi75/lrgb",
        "source_key": "lrgb",
        "introduced_year": 2022,
        "task_metrics": [("node-classification", "F1")],
    },
    {
        "name": "COCO-SP",
        "slug": "coco-sp",
        "full_name": "COCO-SP node classification",
        "short_description": "LRGB MS COCO superpixel node classification benchmark.",
        "description": "COCO-SP is a Long Range Graph Benchmark node "
        "classification dataset built from MS COCO superpixel graphs. The "
        "leaderboard uses macro weighted F1.",
        "homepage": "https://github.com/vijaydwivedi75/lrgb",
        "url": "https://github.com/vijaydwivedi75/lrgb",
        "source_key": "lrgb",
        "introduced_year": 2022,
        "task_metrics": [("node-classification", "F1")],
    },
    {
        "name": "PCQM-Contact",
        "slug": "pcqm-contact",
        "full_name": "PCQM-Contact link prediction",
        "short_description": "LRGB molecular contact link prediction benchmark.",
        "description": "PCQM-Contact is a Long Range Graph Benchmark link "
        "prediction dataset for identifying distant atom pairs that contact in "
        "3D molecular structure. The configured leaderboard uses MRR.",
        "homepage": "https://github.com/vijaydwivedi75/lrgb",
        "url": "https://github.com/vijaydwivedi75/lrgb",
        "source_key": "lrgb",
        "introduced_year": 2022,
        "task_metrics": [("link-prediction", "MRR")],
    },
    # Batch D: MoleculeNet.
    *[
        {
            "name": name,
            "slug": slug,
            "full_name": full_name,
            "short_description": short_description,
            "description": description,
            "homepage": "https://moleculenet.org/datasets-1",
            "url": "https://moleculenet.org/datasets-1",
            "source_key": "moleculenet",
            "introduced_year": 2017,
            "task_metrics": [("molecular-property-prediction", metric)],
        }
        for name, slug, full_name, short_description, description, metric in [
            (
                "BBBP",
                "bbbp",
                "BBBP molecular property prediction",
                "Blood-brain barrier penetration classification from MoleculeNet.",
                "BBBP is a MoleculeNet binary molecular classification task for "
                "predicting blood-brain barrier penetration.",
                "ROC-AUC",
            ),
            (
                "BACE",
                "bace",
                "BACE molecular property prediction",
                "Beta-secretase inhibitor classification from MoleculeNet.",
                "BACE is a MoleculeNet molecular classification benchmark for "
                "beta-secretase inhibitor activity.",
                "ROC-AUC",
            ),
            (
                "ClinTox",
                "clintox",
                "ClinTox molecular property prediction",
                "Clinical trial toxicity classification from MoleculeNet.",
                "ClinTox is a MoleculeNet toxicity classification benchmark "
                "based on clinical trial and FDA approval outcomes.",
                "ROC-AUC",
            ),
            (
                "Tox21",
                "tox21",
                "Tox21 molecular property prediction",
                "Toxicology classification benchmark from MoleculeNet.",
                "Tox21 is a MoleculeNet multi-task molecular toxicity "
                "classification benchmark.",
                "ROC-AUC",
            ),
            (
                "ToxCast",
                "toxcast",
                "ToxCast molecular property prediction",
                "Large-scale molecular toxicity benchmark from MoleculeNet.",
                "ToxCast is a MoleculeNet molecular toxicity classification "
                "benchmark spanning many toxicology assays.",
                "ROC-AUC",
            ),
            (
                "SIDER",
                "sider",
                "SIDER molecular property prediction",
                "Drug side-effect classification benchmark from MoleculeNet.",
                "SIDER is a MoleculeNet molecular classification benchmark "
                "for drug side-effect categories.",
                "ROC-AUC",
            ),
            (
                "ESOL",
                "esol",
                "ESOL molecular property prediction",
                "Aqueous solubility regression benchmark from MoleculeNet.",
                "ESOL is a MoleculeNet molecular regression benchmark for "
                "aqueous solubility prediction.",
                "RMSE",
            ),
            (
                "FreeSolv",
                "freesolv",
                "FreeSolv molecular property prediction",
                "Hydration free energy regression benchmark from MoleculeNet.",
                "FreeSolv is a MoleculeNet molecular regression benchmark for "
                "hydration free energy prediction.",
                "RMSE",
            ),
            (
                "Lipophilicity",
                "lipophilicity",
                "Lipophilicity molecular property prediction",
                "Octanol/water distribution regression benchmark from MoleculeNet.",
                "Lipophilicity is a MoleculeNet molecular regression benchmark "
                "for octanol/water distribution coefficient prediction.",
                "RMSE",
            ),
            (
                "QM9",
                "qm9",
                "QM9 molecular property prediction",
                "Quantum chemistry molecular property regression benchmark.",
                "QM9 is a MoleculeNet quantum chemistry molecular regression "
                "benchmark with multiple small-molecule target properties.",
                "MAE",
            ),
        ]
    ],
    # Batch E: knowledge graph completion.
    {
        "name": "FB15k-237",
        "slug": "fb15k-237",
        "full_name": "FB15k-237 knowledge graph completion",
        "short_description": "Filtered Freebase knowledge graph completion benchmark.",
        "description": "FB15k-237 is a filtered Freebase knowledge graph "
        "completion benchmark that removes many inverse relation shortcuts from "
        "FB15k. The configured leaderboard uses MRR.",
        "homepage": "https://aclanthology.org/W15-4007/",
        "url": "https://aclanthology.org/W15-4007/",
        "external_source": "fb15k-237",
        "introduced_year": 2015,
        "task_metrics": [("knowledge-graph-completion", "MRR")],
    },
    {
        "name": "WN18RR",
        "slug": "wn18rr",
        "full_name": "WN18RR knowledge graph completion",
        "short_description": "Filtered WordNet knowledge graph completion benchmark.",
        "description": "WN18RR is a filtered WordNet knowledge graph completion "
        "benchmark designed to remove inverse relation leakage from WN18. The "
        "configured leaderboard uses MRR.",
        "homepage": "https://arxiv.org/abs/1707.01476",
        "url": "https://arxiv.org/abs/1707.01476",
        "source_key": "conve",
        "introduced_year": 2017,
        "task_metrics": [("knowledge-graph-completion", "MRR")],
    },
    {
        "name": "Wikidata5M",
        "slug": "wikidata5m",
        "full_name": "Wikidata5M knowledge graph completion",
        "short_description": "Large-scale Wikidata knowledge graph benchmark.",
        "description": "Wikidata5M is a large-scale knowledge graph benchmark "
        "introduced with KEPLER for transductive and inductive knowledge graph "
        "completion. The configured leaderboard uses MRR.",
        "homepage": "https://arxiv.org/abs/1911.06136",
        "url": "https://arxiv.org/abs/1911.06136",
        "source_key": "kepler-wikidata5m",
        "introduced_year": 2019,
        "task_metrics": [("knowledge-graph-completion", "MRR")],
    },
    {
        "name": "NELL-995",
        "slug": "nell-995",
        "full_name": "NELL-995 knowledge graph completion",
        "short_description": "NELL knowledge graph completion benchmark.",
        "description": "NELL-995 is a knowledge graph completion benchmark drawn "
        "from the Never-Ending Language Learning knowledge base. The configured "
        "leaderboard uses MRR.",
        "homepage": "https://arxiv.org/abs/1705.02481",
        "url": "https://arxiv.org/abs/1705.02481",
        "source_key": "neural-lp",
        "introduced_year": 2017,
        "task_metrics": [("knowledge-graph-completion", "MRR")],
    },
    # Batch F: Temporal Graph Benchmark.
    *[
        {
            "name": name,
            "slug": slug,
            "full_name": full_name,
            "short_description": short_description,
            "description": description,
            "homepage": homepage,
            "url": homepage,
            "source_key": source_key,
            "introduced_year": year,
            "task_metrics": task_metrics,
        }
        for (
            name,
            slug,
            full_name,
            short_description,
            description,
            homepage,
            source_key,
            year,
            task_metrics,
        ) in [
            (
                "tgbl-wiki",
                "tgbl-wiki",
                "tgbl-wiki temporal link prediction",
                "TGB Wikipedia temporal link prediction benchmark.",
                "tgbl-wiki is a Temporal Graph Benchmark dynamic link "
                "prediction dataset over Wikipedia edit interactions. The "
                "leaderboard uses MRR.",
                "https://tgb.complexdatalab.com/docs/linkprop/",
                "tgb",
                2023,
                [("temporal-graph-learning", "MRR"), ("link-prediction", "MRR")],
            ),
            (
                "tgbl-review",
                "tgbl-review",
                "tgbl-review temporal link prediction",
                "TGB review temporal link prediction benchmark.",
                "tgbl-review is a Temporal Graph Benchmark dynamic link "
                "prediction dataset over review interactions. The leaderboard "
                "uses MRR.",
                "https://tgb.complexdatalab.com/docs/linkprop/",
                "tgb",
                2023,
                [("temporal-graph-learning", "MRR"), ("link-prediction", "MRR")],
            ),
            (
                "tgbl-coin",
                "tgbl-coin",
                "tgbl-coin temporal link prediction",
                "TGB cryptocurrency temporal link prediction benchmark.",
                "tgbl-coin is a Temporal Graph Benchmark dynamic link "
                "prediction dataset over cryptocurrency transaction graphs. "
                "The leaderboard uses MRR.",
                "https://tgb.complexdatalab.com/docs/linkprop/",
                "tgb",
                2023,
                [("temporal-graph-learning", "MRR"), ("link-prediction", "MRR")],
            ),
            (
                "tgbl-comment",
                "tgbl-comment",
                "tgbl-comment temporal link prediction",
                "TGB comment temporal link prediction benchmark.",
                "tgbl-comment is a Temporal Graph Benchmark dynamic link "
                "prediction dataset over online comment interactions. The "
                "leaderboard uses MRR.",
                "https://tgb.complexdatalab.com/docs/linkprop/",
                "tgb",
                2023,
                [("temporal-graph-learning", "MRR"), ("link-prediction", "MRR")],
            ),
            (
                "tgbn-trade",
                "tgbn-trade",
                "tgbn-trade dynamic node property prediction",
                "TGB agriculture trade dynamic node property prediction benchmark.",
                "tgbn-trade is a Temporal Graph Benchmark dynamic node property "
                "prediction dataset over international agriculture trade. The "
                "official metric is NDCG@10.",
                "https://tgb.complexdatalab.com/docs/nodeprop/",
                "tgb",
                2023,
                [("temporal-graph-learning", "NDCG@10")],
            ),
            (
                "tgbn-genre",
                "tgbn-genre",
                "tgbn-genre dynamic node property prediction",
                "TGB music-genre dynamic node property prediction benchmark.",
                "tgbn-genre is a Temporal Graph Benchmark dynamic node property "
                "prediction dataset over user and music-genre interactions. The "
                "official metric is NDCG@10.",
                "https://tgb.complexdatalab.com/docs/nodeprop/",
                "tgb",
                2023,
                [("temporal-graph-learning", "NDCG@10")],
            ),
            (
                "tkgl-wikidata",
                "tkgl-wikidata",
                "tkgl-wikidata temporal knowledge graph prediction",
                "TGB 2.0 temporal knowledge graph benchmark.",
                "tkgl-wikidata is a TGB 2.0 temporal knowledge graph benchmark "
                "for predicting future links in Wikidata-style multi-relational "
                "temporal graphs. The configured leaderboard uses MRR.",
                "https://tgb.complexdatalab.com/docs/tkg/",
                "tgb2",
                2024,
                [
                    ("temporal-graph-learning", "MRR"),
                    ("knowledge-graph-completion", "MRR"),
                ],
            ),
            (
                "thgl-software",
                "thgl-software",
                "thgl-software temporal heterogeneous graph prediction",
                "TGB 2.0 temporal heterogeneous graph benchmark.",
                "thgl-software is a TGB 2.0 temporal heterogeneous graph "
                "benchmark for future link prediction in typed software graphs. "
                "The configured leaderboard uses MRR.",
                "https://tgb.complexdatalab.com/docs/thg/",
                "tgb2",
                2024,
                [("temporal-graph-learning", "MRR")],
            ),
        ]
    ],
]
