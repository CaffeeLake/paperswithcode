"""Declarative task, benchmark, and evaluation specs for recommendation coverage."""

from datetime import date
from typing import Any

TASKS: list[dict[str, Any]] = [
    {
        "name": "Recommendation Systems",
        "slug": "recommendation-systems",
        "parent": None,
        "area": "Other",
        "keywords": (
            "recommender, recommender system, recommendation system, "
            "personalized recommendation, collaborative filtering, item "
            "recommendation, product recommendation, content recommendation, "
            "recommendation engine, top-N recommendation, implicit feedback, "
            "explicit feedback, sequential recommendation, session "
            "recommendation, click-through rate prediction, CTR prediction, "
            "learning to rank, ranking model, generative recommendation, "
            "semantic ID, industrial recommendation"
        ),
        "description": (
            "Recommendation Systems study how to retrieve, rank, and personalize "
            "items for users from interaction, content, context, and feedback "
            "signals. This hub separates collaborative filtering, sequential and "
            "session recommendation, click-through-rate prediction, classical "
            "learning-to-rank, and generative recommendation so benchmark "
            "protocols remain comparable."
        ),
    },
    {
        "name": "Collaborative Filtering",
        "slug": "collaborative-filtering",
        "parent": "recommendation-systems",
        "area": "Other",
        "keywords": (
            "collaborative filtering, implicit collaborative filtering, matrix "
            "factorization, user item recommendation, top-N recommendation, "
            "neural collaborative filtering, graph collaborative filtering, "
            "LightGCN, NGCF, NeuMF"
        ),
        "description": (
            "Collaborative Filtering predicts user preference from user-item "
            "interaction matrices, including explicit rating prediction and "
            "implicit top-N ranking. Rating-prediction, sampled-negative ranking, "
            "and full-catalog ranking are tracked on separate leaderboards."
        ),
    },
    {
        "name": "Sequential Recommendation",
        "slug": "sequential-recommendation",
        "parent": "recommendation-systems",
        "area": "Other",
        "keywords": (
            "sequential recommendation, next item recommendation, next-item "
            "recommendation, user sequence recommendation, SASRec, BERT4Rec, "
            "S3-Rec, CL4SRec, HSTU"
        ),
        "description": (
            "Sequential Recommendation predicts future items from an ordered user "
            "history. Leaderboards distinguish chronological sampled-negative "
            "evaluation from full-catalog evaluation."
        ),
    },
    {
        "name": "Session-Based Recommendation",
        "slug": "session-based-recommendation",
        "parent": "recommendation-systems",
        "area": "Other",
        "keywords": (
            "session-based recommendation, session based recommendation, session "
            "recommendation, anonymous session recommendation, next click "
            "recommendation, GRU4Rec, NARM, SR-GNN, YOOCHOOSE, Diginetica"
        ),
        "description": (
            "Session-Based Recommendation predicts the next item or click inside "
            "short anonymous sessions, usually with time-split session logs and "
            "full-candidate ranking metrics such as Precision@20 and MRR@20."
        ),
    },
    {
        "name": "Click-Through Rate Prediction",
        "slug": "click-through-rate-prediction",
        "parent": "recommendation-systems",
        "area": "Other",
        "keywords": (
            "click-through rate prediction, click through rate prediction, CTR "
            "prediction, ad click prediction, conversion rate prediction, CVR "
            "prediction, feature interaction, DeepFM, DCN, xDeepFM, AutoInt, DLRM"
        ),
        "description": (
            "Click-Through Rate Prediction estimates the probability of a user "
            "clicking an item or advertisement from dense, categorical, sequence, "
            "and context features. Public offline AUC and LogLoss benchmarks are "
            "kept separate from private online A/B-test metrics."
        ),
    },
    {
        "name": "Learning to Rank",
        "slug": "learning-to-rank",
        "parent": "recommendation-systems",
        "area": "Other",
        "keywords": (
            "learning to rank, learning-to-rank, LTR, LambdaMART, RankNet, "
            "ListNet, ListMLE, coordinate ascent ranking, LETOR, MSLR-WEB10K, "
            "MSLR-WEB30K, Yahoo Learning to Rank"
        ),
        "description": (
            "Learning to Rank learns scoring functions that order documents, "
            "ads, products, or items for a query or user context. Classical "
            "feature-based LETOR/MSLR/Yahoo protocols are separated from neural "
            "text reranking benchmarks that live under retrieval tasks."
        ),
    },
    {
        "name": "Generative Recommendation",
        "slug": "generative-recommendation",
        "parent": "recommendation-systems",
        "area": "Other",
        "keywords": (
            "generative recommendation, generative retrieval recommendation, "
            "semantic ID recommendation, semantic IDs, LLM recommendation, "
            "recommendation foundation model, TIGER, P5, LETTER, OpenOneRec, "
            "RecIF-Bench, Yambda"
        ),
        "description": (
            "Generative Recommendation formulates recommendation as generating "
            "item identifiers, semantic IDs, text, or actions with sequence "
            "models and large language models. It includes public semantic-ID "
            "benchmarks and newer foundation-model style recommendation suites."
        ),
    },
    {
        "name": "Knowledge-Aware and Multimodal Recommendation",
        "slug": "knowledge-aware-multimodal-recommendation",
        "parent": "recommendation-systems",
        "area": "Other",
        "keywords": (
            "knowledge-aware recommendation, knowledge graph recommendation, "
            "multimodal recommendation, visual recommendation, KGAT, KGCN, "
            "RippleNet, LATTICE, FREEDOM, MMGCN"
        ),
        "description": (
            "Knowledge-Aware and Multimodal Recommendation augments interaction "
            "data with knowledge graphs, images, text, audio, or other item and "
            "user modalities. Plain interaction-only leaderboards are not mixed "
            "with side-information variants."
        ),
    },
]

METRICS = [
    ("Recall@20", "higher_is_better", "0-1", "Recall at rank 20."),
    (
        "NDCG@20",
        "higher_is_better",
        "0-1",
        "Normalized discounted cumulative gain at rank 20.",
    ),
    ("HR@10", "higher_is_better", "0-1", "Hit rate at rank 10."),
    ("Hit@10", "higher_is_better", "0-1", "Hit rate at rank 10."),
    (
        "NDCG@10",
        "higher_is_better",
        "0-1",
        "Normalized discounted cumulative gain at rank 10.",
    ),
    ("Precision@20", "higher_is_better", "0-1", "Precision at rank 20."),
    ("MRR@20", "higher_is_better", "0-1", "Mean reciprocal rank at rank 20."),
    ("AUC", "higher_is_better", "0-1", "Area under the ROC curve."),
    ("LogLoss", "lower_is_better", "unbounded", "Binary cross entropy / log loss."),
    ("Log Loss", "lower_is_better", "unbounded", "Binary cross entropy / log loss."),
    ("MAP", "higher_is_better", "0-1", "Mean average precision."),
    (
        "NDCG@1",
        "higher_is_better",
        "0-1",
        "Normalized discounted cumulative gain at rank 1.",
    ),
    (
        "NDCG@3",
        "higher_is_better",
        "0-1",
        "Normalized discounted cumulative gain at rank 3.",
    ),
    (
        "NDCG@5",
        "higher_is_better",
        "0-1",
        "Normalized discounted cumulative gain at rank 5.",
    ),
    ("ERR", "higher_is_better", "0-1", "Expected reciprocal rank."),
    ("Recall@5", "higher_is_better", "0-1", "Recall at rank 5."),
    ("Recall@10", "higher_is_better", "0-1", "Recall at rank 10."),
    ("Recall@32", "higher_is_better", "0-1", "Recall at rank 32."),
    (
        "NDCG@100",
        "higher_is_better",
        "0-1",
        "Normalized discounted cumulative gain at rank 100.",
    ),
    ("Coverage", "higher_is_better", "0-1", "Catalog coverage."),
]

SOURCE_ARXIV = {
    "ncf": "1708.05031",
    "lightgcn": "2002.02126",
    "sasrec": "1808.09781",
    "srgnn": "1811.00855",
    "dcnv2": "2008.13535",
    "autoint": "1810.11921",
    "tiger": "2305.05065",
    "hstu": "2402.17152",
    "setrec": "2502.10833",
    "yambda": "2505.22238",
    "openonerec": "2512.24762",
}

EXTERNAL_SOURCES = {
    "letor": {
        "title": "LETOR 4.0 Benchmark Datasets",
        "source_url": "https://www.microsoft.com/en-us/research/project/letor-learning-rank-information-retrieval/",
        "date_published": date(2009, 7, 1),
        "abstract": (
            "LETOR 4.0 provides standard feature-based learning-to-rank datasets "
            "including MQ2007 and MQ2008 with official folds and ranking metrics."
        ),
    },
    "mslr": {
        "title": "Microsoft Learning to Rank Datasets",
        "source_url": "https://www.microsoft.com/en-us/research/project/mslr/",
        "date_published": date(2010, 7, 1),
        "abstract": (
            "The Microsoft Learning to Rank datasets provide WEB10K and WEB30K "
            "query-document relevance data with 136 ranking features and official "
            "folds."
        ),
    },
    "yahoo-ltr": {
        "title": "Yahoo! Learning to Rank Challenge",
        "source_url": "https://webscope.sandbox.yahoo.com/catalog.php?datatype=c",
        "date_published": date(2010, 6, 1),
        "abstract": (
            "The Yahoo! Learning to Rank Challenge released large-scale "
            "feature-based ranking datasets with official train, validation, and "
            "test splits."
        ),
    },
}

BENCHMARKS: list[dict[str, Any]] = [
    {
        "name": "Gowalla (NGCF/LightGCN Full Ranking)",
        "slug": "gowalla-ngcf-lightgcn-full-ranking",
        "task_slugs": ["collaborative-filtering"],
        "source_key": "lightgcn",
        "metrics": ["Recall@20", "NDCG@20"],
        "introduced_date": date(2020, 2, 6),
        "homepage": "https://github.com/gusye1234/LightGCN-PyTorch",
        "short_description": "Gowalla implicit-feedback full-ranking protocol used by NGCF and LightGCN.",
        "description": (
            "Gowalla full-ranking benchmark using the released NGCF/LightGCN "
            "implicit-feedback split. Scores rank all unobserved candidate items; "
            "sampled-negative and graph side-information variants are excluded."
        ),
    },
    {
        "name": "Yelp2018 (NGCF/LightGCN Full Ranking)",
        "slug": "yelp2018-ngcf-lightgcn-full-ranking",
        "task_slugs": ["collaborative-filtering"],
        "source_key": "lightgcn",
        "metrics": ["Recall@20", "NDCG@20"],
        "introduced_date": date(2020, 2, 6),
        "homepage": "https://github.com/gusye1234/LightGCN-PyTorch",
        "short_description": "Yelp2018 implicit-feedback full-ranking protocol used by NGCF and LightGCN.",
        "description": (
            "Yelp2018 full-ranking benchmark using the released NGCF/LightGCN "
            "implicit-feedback split. Scores are not mixed with rating-prediction, "
            "sampled-negative, or KG/multimodal variants."
        ),
    },
    {
        "name": "Amazon-Book (NGCF/LightGCN Full Ranking)",
        "slug": "amazon-book-ngcf-lightgcn-full-ranking",
        "task_slugs": ["collaborative-filtering"],
        "source_key": "lightgcn",
        "metrics": ["Recall@20", "NDCG@20"],
        "introduced_date": date(2020, 2, 6),
        "homepage": "https://github.com/gusye1234/LightGCN-PyTorch",
        "short_description": "Amazon-Book implicit-feedback full-ranking protocol used by NGCF and LightGCN.",
        "description": (
            "Amazon-Book full-ranking benchmark using the released NGCF/LightGCN "
            "split over implicit interactions. Plain interaction-only results are "
            "kept separate from KGAT and multimodal Amazon variants."
        ),
    },
    {
        "name": "MovieLens-1M (NCF 100-Negative Leave-One-Out)",
        "slug": "movielens-1m-ncf-100-negative-loo",
        "task_slugs": ["collaborative-filtering"],
        "source_key": "ncf",
        "metrics": ["HR@10", "NDCG@10"],
        "introduced_date": date(2017, 8, 16),
        "homepage": "https://grouplens.org/datasets/movielens/1m/",
        "short_description": "MovieLens-1M leave-one-out protocol with 100 sampled negatives.",
        "description": (
            "MovieLens-1M sampled ranking protocol from Neural Collaborative "
            "Filtering: leave-one-out per user with 100 sampled negative items. "
            "Full-catalog and explicit-rating RMSE results are excluded."
        ),
    },
    {
        "name": "MovieLens-1M (SASRec 100-Negative Sequential)",
        "slug": "movielens-1m-sasrec-100-negative-sequential",
        "task_slugs": ["sequential-recommendation"],
        "source_key": "sasrec",
        "metrics": ["HR@10", "NDCG@10"],
        "introduced_date": date(2018, 8, 20),
        "homepage": "https://grouplens.org/datasets/movielens/1m/",
        "short_description": "Chronological next-item MovieLens-1M protocol with sampled negatives.",
        "description": (
            "MovieLens-1M sequential next-item benchmark following SASRec-style "
            "chronological leave-one-out evaluation with 100 sampled negatives."
        ),
    },
    {
        "name": "Amazon Beauty (SASRec 100-Negative Sequential)",
        "slug": "amazon-beauty-sasrec-100-negative-sequential",
        "task_slugs": ["sequential-recommendation"],
        "source_key": "sasrec",
        "metrics": ["Hit@10", "HR@10", "NDCG@10"],
        "introduced_date": date(2018, 8, 20),
        "homepage": "https://cseweb.ucsd.edu/~jmcauley/datasets/amazon_v2/",
        "short_description": "Amazon Beauty chronological next-item protocol with sampled negatives.",
        "description": (
            "Amazon Beauty sequential recommendation benchmark using "
            "SASRec-style chronological evaluation with sampled negatives. "
            "Amazon release, core filtering, and sampled-negative policy must be "
            "kept explicit."
        ),
    },
    {
        "name": "Amazon Games (SASRec 100-Negative Sequential)",
        "slug": "amazon-games-sasrec-100-negative-sequential",
        "task_slugs": ["sequential-recommendation"],
        "source_key": "sasrec",
        "metrics": ["Hit@10", "HR@10", "NDCG@10"],
        "introduced_date": date(2018, 8, 20),
        "homepage": "https://cseweb.ucsd.edu/~jmcauley/datasets/amazon_v2/",
        "short_description": "Amazon Games chronological next-item protocol with sampled negatives.",
        "description": (
            "Amazon Games sequential recommendation benchmark using a "
            "chronological leave-one-out setup with sampled negatives, following "
            "the SASRec comparison lineage."
        ),
    },
    {
        "name": "Steam (SASRec 100-Negative Sequential)",
        "slug": "steam-sasrec-100-negative-sequential",
        "task_slugs": ["sequential-recommendation"],
        "source_key": "sasrec",
        "metrics": ["Hit@10", "NDCG@10"],
        "introduced_date": date(2018, 8, 20),
        "homepage": "https://cseweb.ucsd.edu/~jmcauley/datasets.html",
        "short_description": "Steam chronological next-item protocol with sampled negatives.",
        "description": (
            "Steam next-item recommendation benchmark as reported in the "
            "SASRec-style sampled-negative sequential recommendation lineage."
        ),
    },
    {
        "name": "YOOCHOOSE 1/64 (SR-GNN Session)",
        "slug": "yoochoose-1-64-srgnn-session",
        "task_slugs": ["session-based-recommendation"],
        "source_key": "srgnn",
        "metrics": ["Precision@20", "MRR@20"],
        "introduced_date": date(2018, 11, 2),
        "homepage": "https://2015.recsyschallenge.com/challenge.html",
        "short_description": "YOOCHOOSE 1/64 session recommendation protocol.",
        "description": (
            "YOOCHOOSE 1/64 session-based recommendation benchmark using "
            "SR-GNN-style preprocessing and full candidate evaluation with "
            "Precision@20 and MRR@20."
        ),
    },
    {
        "name": "YOOCHOOSE 1/4 (SR-GNN Session)",
        "slug": "yoochoose-1-4-srgnn-session",
        "task_slugs": ["session-based-recommendation"],
        "source_key": "srgnn",
        "metrics": ["Precision@20", "MRR@20"],
        "introduced_date": date(2018, 11, 2),
        "homepage": "https://2015.recsyschallenge.com/challenge.html",
        "short_description": "YOOCHOOSE 1/4 session recommendation protocol.",
        "description": (
            "YOOCHOOSE 1/4 session-based recommendation benchmark. It is kept "
            "separate from YOOCHOOSE 1/64 because the training fraction changes "
            "the protocol and scores."
        ),
    },
    {
        "name": "Diginetica (SR-GNN Session)",
        "slug": "diginetica-srgnn-session",
        "task_slugs": ["session-based-recommendation"],
        "source_key": "srgnn",
        "metrics": ["Precision@20", "MRR@20"],
        "introduced_date": date(2018, 11, 2),
        "homepage": "https://competitions.codalab.org/competitions/11161",
        "short_description": "Diginetica session recommendation protocol.",
        "description": (
            "Diginetica session-based recommendation benchmark using the "
            "SR-GNN-style time split and full candidate evaluation."
        ),
    },
    {
        "name": "Criteo (DCNv2 CTR Protocol)",
        "slug": "criteo-dcnv2-ctr-protocol",
        "task_slugs": ["click-through-rate-prediction"],
        "source_key": "dcnv2",
        "metrics": ["AUC", "Log Loss", "LogLoss"],
        "introduced_date": date(2020, 8, 31),
        "homepage": "https://ailab.criteo.com/download-criteo-1tb-click-logs-dataset/",
        "short_description": "Criteo CTR prediction protocol used by DCN/DCNv2 and descendants.",
        "description": (
            "Criteo CTR benchmark for public offline feature-interaction models, "
            "tracking AUC and LogLoss under the DCNv2-style protocol. Terabyte, "
            "FuxiCTR x1/x2/x4, and private company splits are separate protocols."
        ),
    },
    {
        "name": "Avazu (Chronological CTR)",
        "slug": "avazu-chronological-ctr",
        "task_slugs": ["click-through-rate-prediction"],
        "source_key": "autoint",
        "metrics": ["AUC", "LogLoss"],
        "introduced_date": date(2018, 10, 29),
        "homepage": "https://www.kaggle.com/c/avazu-ctr-prediction",
        "short_description": "Avazu click-through-rate prediction with chronological splitting.",
        "description": (
            "Avazu public CTR benchmark with chronological splitting and "
            "feature preprocessing stated by each source paper. Framework reruns "
            "and alternative FuxiCTR variants are separate protocols."
        ),
    },
    {
        "name": "KDD12 CTR (AutoInt Protocol)",
        "slug": "kdd12-autoint-ctr-protocol",
        "task_slugs": ["click-through-rate-prediction"],
        "source_key": "autoint",
        "metrics": ["AUC", "Log Loss"],
        "introduced_date": date(2018, 10, 29),
        "homepage": "https://www.kddcup2012.org/c/kddcup2012-track2",
        "short_description": "KDD Cup 2012 Track 2 CTR protocol used in AutoInt-era papers.",
        "description": (
            "KDD12 CTR benchmark for feature-interaction models using the "
            "AutoInt-era preprocessing and split family. LogLoss and AUC are "
            "recorded only when the source reports the same protocol."
        ),
    },
    {
        "name": "LETOR 4.0 MQ2007 (Five-Fold Mean)",
        "slug": "letor-4-mq2007-five-fold-mean",
        "task_slugs": ["learning-to-rank"],
        "external_source_key": "letor",
        "metrics": ["MAP", "NDCG@1", "NDCG@3", "NDCG@5", "NDCG@10"],
        "introduced_date": date(2009, 7, 1),
        "homepage": "https://www.microsoft.com/en-us/research/project/letor-learning-rank-information-retrieval/",
        "short_description": "LETOR 4.0 MQ2007 official five-fold learning-to-rank protocol.",
        "description": (
            "LETOR 4.0 MQ2007 with QueryLevelNorm and official five-fold mean "
            "ranking metrics. Fold-1-only results are not mixed into this page."
        ),
    },
    {
        "name": "LETOR 4.0 MQ2008 (Five-Fold Mean)",
        "slug": "letor-4-mq2008-five-fold-mean",
        "task_slugs": ["learning-to-rank"],
        "external_source_key": "letor",
        "metrics": ["MAP", "NDCG@1", "NDCG@3", "NDCG@5", "NDCG@10"],
        "introduced_date": date(2009, 7, 1),
        "homepage": "https://www.microsoft.com/en-us/research/project/letor-learning-rank-information-retrieval/",
        "short_description": "LETOR 4.0 MQ2008 official five-fold learning-to-rank protocol.",
        "description": (
            "LETOR 4.0 MQ2008 with QueryLevelNorm and official five-fold mean "
            "ranking metrics. It is separate from MQ2007 and from single-fold "
            "reports."
        ),
    },
    {
        "name": "MSLR-WEB10K (Five-Fold Mean)",
        "slug": "mslr-web10k-five-fold-mean",
        "task_slugs": ["learning-to-rank"],
        "external_source_key": "mslr",
        "metrics": ["NDCG@1", "NDCG@3", "NDCG@5", "NDCG@10"],
        "introduced_date": date(2010, 7, 1),
        "homepage": "https://www.microsoft.com/en-us/research/project/mslr/",
        "short_description": "MSLR-WEB10K official five-fold learning-to-rank protocol.",
        "description": (
            "MSLR-WEB10K feature-based learning-to-rank benchmark with 136 "
            "features, labels 0-4, and official five-fold mean NDCG metrics."
        ),
    },
    {
        "name": "MSLR-WEB30K (Five-Fold Mean)",
        "slug": "mslr-web30k-five-fold-mean",
        "task_slugs": ["learning-to-rank"],
        "external_source_key": "mslr",
        "metrics": ["NDCG@1", "NDCG@3", "NDCG@5", "NDCG@10"],
        "introduced_date": date(2010, 7, 1),
        "homepage": "https://www.microsoft.com/en-us/research/project/mslr/",
        "short_description": "MSLR-WEB30K official five-fold learning-to-rank protocol.",
        "description": (
            "MSLR-WEB30K feature-based learning-to-rank benchmark. Fold-1-only "
            "and five-fold mean results should be split if both are imported."
        ),
    },
    {
        "name": "Yahoo Learning to Rank Challenge Set 1",
        "slug": "yahoo-learning-to-rank-challenge-set-1",
        "task_slugs": ["learning-to-rank"],
        "external_source_key": "yahoo-ltr",
        "metrics": ["NDCG@10", "ERR"],
        "introduced_date": date(2010, 6, 1),
        "homepage": "https://webscope.sandbox.yahoo.com/catalog.php?datatype=c",
        "short_description": "Yahoo Learning to Rank Challenge Set 1 protocol.",
        "description": (
            "Yahoo Learning to Rank Challenge Set 1 with official train, "
            "validation, and test splits. Set 2 and web-search reranking tasks "
            "are separate benchmark pages."
        ),
    },
    {
        "name": "TIGER Amazon Beauty (Full Catalog)",
        "slug": "tiger-amazon-beauty-full-catalog",
        "task_slugs": ["generative-recommendation"],
        "source_key": "tiger",
        "metrics": ["Recall@5", "Recall@10", "NDCG@5", "NDCG@10"],
        "introduced_date": date(2023, 5, 8),
        "homepage": "https://github.com/jeykigung/P5",
        "short_description": "TIGER semantic-ID generative recommendation on Amazon Beauty.",
        "description": (
            "TIGER Amazon Beauty uses semantic IDs, chronological leave-one-out "
            "evaluation, and full-catalog ranking over Amazon Reviews 2014 5-core "
            "style data."
        ),
    },
    {
        "name": "TIGER Amazon Sports (Full Catalog)",
        "slug": "tiger-amazon-sports-full-catalog",
        "task_slugs": ["generative-recommendation"],
        "source_key": "tiger",
        "metrics": ["Recall@5", "Recall@10", "NDCG@5", "NDCG@10"],
        "introduced_date": date(2023, 5, 8),
        "homepage": "https://github.com/jeykigung/P5",
        "short_description": "TIGER semantic-ID generative recommendation on Amazon Sports.",
        "description": "TIGER Amazon Sports full-catalog semantic-ID recommendation benchmark.",
    },
    {
        "name": "TIGER Amazon Toys (Full Catalog)",
        "slug": "tiger-amazon-toys-full-catalog",
        "task_slugs": ["generative-recommendation"],
        "source_key": "tiger",
        "metrics": ["Recall@5", "Recall@10", "NDCG@5", "NDCG@10"],
        "introduced_date": date(2023, 5, 8),
        "homepage": "https://github.com/jeykigung/P5",
        "short_description": "TIGER semantic-ID generative recommendation on Amazon Toys.",
        "description": "TIGER Amazon Toys full-catalog semantic-ID recommendation benchmark.",
    },
    {
        "name": "HSTU MovieLens-20M (Full Catalog)",
        "slug": "hstu-movielens-20m-full-catalog",
        "task_slugs": ["sequential-recommendation", "generative-recommendation"],
        "source_key": "hstu",
        "metrics": ["HR@10", "NDCG@10", "NDCG@100"],
        "introduced_date": date(2024, 2, 27),
        "homepage": "https://github.com/facebookresearch/generative-recommenders",
        "short_description": "HSTU full-catalog sequential recommendation on MovieLens-20M.",
        "description": (
            "HSTU MovieLens-20M full-catalog benchmark. Sampled-negative "
            "MovieLens leaderboards are not mixed with this full-catalog protocol."
        ),
    },
    {
        "name": "SETRec Cold-Start Recommendation",
        "slug": "setrec-cold-start-recommendation",
        "task_slugs": ["generative-recommendation"],
        "source_key": "setrec",
        "metrics": ["Recall@5", "Recall@10", "NDCG@5", "NDCG@10"],
        "introduced_date": date(2025, 2, 15),
        "homepage": "https://arxiv.org/abs/2502.10833",
        "short_description": "SETRec all/warm/cold generative recommendation protocol.",
        "description": (
            "SETRec evaluates cold-start and warm-start generative recommendation "
            "with all/warm/cold partitions. Dataset and partition must be preserved "
            "in methodology or split into narrower pages as adoption grows."
        ),
    },
    {
        "name": "Yambda-50M Ranking",
        "slug": "yambda-50m-ranking",
        "task_slugs": ["generative-recommendation", "learning-to-rank"],
        "source_key": "yambda",
        "metrics": ["NDCG@10", "NDCG@100", "Recall@10", "Coverage"],
        "introduced_date": date(2025, 5, 28),
        "homepage": "https://arxiv.org/abs/2505.22238",
        "short_description": "Yambda-50M public multimodal ranking and retrieval benchmark.",
        "description": (
            "Yambda-50M is the smaller public Yambda ranking slice. Scale, "
            "feedback type, and temporal split must be recorded for each result."
        ),
    },
    {
        "name": "RecIF-Bench",
        "slug": "recif-bench",
        "task_slugs": ["generative-recommendation"],
        "source_key": "openonerec",
        "metrics": ["Recall@32", "AUC"],
        "introduced_date": date(2025, 12, 31),
        "homepage": "https://huggingface.co/OpenOneRec",
        "short_description": "OpenOneRec recommendation instruction-following benchmark family.",
        "description": (
            "RecIF-Bench evaluates recommendation instruction-following across "
            "OpenOneRec public subsets. Video, ads, product, retrieval, ranking, "
            "and generation subsets should not be collapsed into one score when "
            "importing detailed rows."
        ),
    },
]

MAJOR_PAPER_TASKS = {
    "1205.2618": ["collaborative-filtering"],  # BPR
    "1708.05031": ["collaborative-filtering"],
    "1802.05814": ["collaborative-filtering"],
    "1905.08108": ["collaborative-filtering"],
    "1905.03375": ["collaborative-filtering"],
    "1912.11160": ["collaborative-filtering"],
    "2002.02126": ["collaborative-filtering"],
    "2110.15114": ["collaborative-filtering"],
    "2109.12613": ["collaborative-filtering"],
    "1511.06939": ["session-based-recommendation"],
    "1711.04725": ["session-based-recommendation"],
    "1808.09781": ["sequential-recommendation"],
    "1811.00855": ["session-based-recommendation"],
    "1904.06690": ["sequential-recommendation"],
    "2008.07873": ["sequential-recommendation"],
    "2107.00852": ["session-based-recommendation"],
    "2110.05217": ["sequential-recommendation"],
    "1606.07792": ["click-through-rate-prediction"],
    "1611.00144": ["click-through-rate-prediction"],
    "1703.04247": ["click-through-rate-prediction"],
    "1706.06978": ["click-through-rate-prediction"],
    "1708.05123": ["click-through-rate-prediction"],
    "1803.05170": ["click-through-rate-prediction"],
    "1809.03672": ["click-through-rate-prediction"],
    "1810.11921": ["click-through-rate-prediction"],
    "1906.00091": ["click-through-rate-prediction"],
    "2008.13535": ["click-through-rate-prediction"],
    "2304.00902": ["click-through-rate-prediction"],
    "2203.13366": ["generative-recommendation"],
    "2305.05065": ["generative-recommendation"],
    "2405.07314": ["generative-recommendation"],
    "2409.12740": ["generative-recommendation"],
    "2402.17152": ["sequential-recommendation", "generative-recommendation"],
    "2502.10833": ["generative-recommendation"],
    "2503.05493": ["generative-recommendation", "sequential-recommendation"],
    "2503.24289": ["generative-recommendation"],
    "2505.22238": ["generative-recommendation", "learning-to-rank"],
    "2507.22224": ["generative-recommendation"],
    "2512.24762": ["generative-recommendation"],
    "2604.19550": ["click-through-rate-prediction"],
    "2601.20083": ["click-through-rate-prediction"],
    "1803.03467": ["knowledge-aware-multimodal-recommendation"],
    "1901.08907": ["knowledge-aware-multimodal-recommendation"],
    "1904.12575": ["knowledge-aware-multimodal-recommendation"],
    "1905.07854": ["knowledge-aware-multimodal-recommendation"],
}

RECENT_PAPER_TASKS = {
    # 2026 frontier papers already present in the local corpus.
    "2606.16838": ["learning-to-rank"],
    "2606.14142": ["generative-recommendation"],
    "2606.10156": ["generative-recommendation"],
    "2606.00125": ["knowledge-aware-multimodal-recommendation"],
    "2605.28293": ["recommendation-systems"],
    "2604.25032": ["recommendation-systems"],
    "2604.14878": ["generative-recommendation"],
    "2604.04976": [
        "generative-recommendation",
        "knowledge-aware-multimodal-recommendation",
    ],
    "2604.00590": ["recommendation-systems"],
    "2603.19809": ["generative-recommendation"],
    "2603.12935": ["recommendation-systems"],
    "2603.02730": ["generative-recommendation"],
    "2603.00416": ["generative-recommendation"],
    "2602.20723": ["knowledge-aware-multimodal-recommendation"],
    "2602.20093": ["sequential-recommendation"],
    "2602.18283": ["sequential-recommendation"],
    "2602.16938": ["recommendation-systems"],
    "2602.16587": ["generative-recommendation"],
    "2602.12612": ["generative-recommendation"],
    "2602.10445": ["generative-recommendation", "click-through-rate-prediction"],
    "2602.11605": ["generative-recommendation"],
    "2602.12041": ["click-through-rate-prediction"],
    "2602.12129": ["knowledge-aware-multimodal-recommendation"],
    "2602.11664": ["generative-recommendation"],
    "2602.10699": ["generative-recommendation"],
    "2602.10226": ["recommendation-systems"],
    "2602.08837": ["generative-recommendation"],
    "2602.07298": ["generative-recommendation"],
    "2602.06563": ["learning-to-rank"],
    "2602.03713": [
        "generative-recommendation",
        "knowledge-aware-multimodal-recommendation",
    ],
    "2602.02338": ["generative-recommendation"],
    "2602.00682": [
        "generative-recommendation",
        "knowledge-aware-multimodal-recommendation",
    ],
    "2601.21105": ["generative-recommendation"],
    "2601.19965": ["click-through-rate-prediction"],
    "2601.19711": ["generative-recommendation"],
    "2601.19585": ["recommendation-systems"],
    "2601.17438": ["generative-recommendation"],
    "2601.16815": ["collaborative-filtering"],
    "2601.16556": ["sequential-recommendation", "generative-recommendation"],
    "2601.08816": ["generative-recommendation"],
    "2601.03479": ["sequential-recommendation"],
    "2601.03153": ["sequential-recommendation"],
    "2601.00930": ["recommendation-systems"],
    # Late-2025 papers from the current frontier slice.
    "2512.24366": ["recommendation-systems"],
    "2512.21543": [
        "generative-recommendation",
        "knowledge-aware-multimodal-recommendation",
    ],
    "2512.21257": ["sequential-recommendation"],
    "2512.14503": ["generative-recommendation"],
    "2512.14036": ["sequential-recommendation"],
    "2512.14034": ["sequential-recommendation"],
    "2512.13120": [
        "collaborative-filtering",
        "knowledge-aware-multimodal-recommendation",
    ],
    "2512.12858": ["generative-recommendation"],
    "2512.10388": ["sequential-recommendation", "generative-recommendation"],
    "2504.12007": ["generative-recommendation"],
}

EVALS: list[dict[str, Any]] = [
    # Collaborative filtering full-ranking spine.
    {
        "paper_arxiv": "1905.08108",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "gowalla-ngcf-lightgcn-full-ranking",
        "model_name": "NGCF",
        "metric": "Recall@20",
        "score": "0.1570",
        "extra": {"NDCG@20": "0.1327"},
        "methodology": "NGCF/LightGCN released Gowalla split; full ranking over unobserved items.",
    },
    {
        "paper_arxiv": "2002.02126",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "gowalla-ngcf-lightgcn-full-ranking",
        "model_name": "LightGCN",
        "metric": "Recall@20",
        "score": "0.1830",
        "extra": {"NDCG@20": "0.1554"},
        "methodology": "LightGCN paper/code protocol on Gowalla; full-ranking Recall@20/NDCG@20.",
    },
    {
        "paper_arxiv": "2110.15114",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "gowalla-ngcf-lightgcn-full-ranking",
        "model_name": "UltraGCN",
        "metric": "Recall@20",
        "score": "0.1862",
        "extra": {"NDCG@20": "0.1580"},
        "methodology": "UltraGCN source row on the NGCF/LightGCN Gowalla full-ranking split.",
    },
    {
        "paper_arxiv": "2109.12613",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "gowalla-ngcf-lightgcn-full-ranking",
        "model_name": "SimpleX",
        "metric": "Recall@20",
        "score": "0.1872",
        "extra": {"NDCG@20": "0.1557"},
        "methodology": "SimpleX source row on the NGCF/LightGCN Gowalla full-ranking split.",
    },
    {
        "paper_arxiv": "2108.06208",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "gowalla-ngcf-lightgcn-full-ranking",
        "model_name": "LT-OCF",
        "metric": "Recall@20",
        "score": "0.1875",
        "extra": {"NDCG@20": "0.1574"},
        "methodology": "LT-OCF source row on the NGCF/LightGCN Gowalla full-ranking split.",
    },
    {
        "paper_arxiv": "2211.09324",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "gowalla-ngcf-lightgcn-full-ranking",
        "model_name": "BSPM-EM",
        "metric": "Recall@20",
        "score": "0.1920",
        "extra": {"NDCG@20": "0.1597"},
        "methodology": "BSPM source row on the NGCF/LightGCN Gowalla full-ranking split.",
    },
    {
        "paper_arxiv": "2402.11523",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "gowalla-ngcf-lightgcn-full-ranking",
        "model_name": "NESCL",
        "metric": "Recall@20",
        "score": "0.1917",
        "extra": {"NDCG@20": "0.1617"},
        "methodology": "NESCL source row on the NGCF/LightGCN Gowalla full-ranking split.",
    },
    {
        "paper_arxiv": "2002.02126",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "yelp2018-ngcf-lightgcn-full-ranking",
        "model_name": "LightGCN",
        "metric": "Recall@20",
        "score": "0.0649",
        "extra": {"NDCG@20": "0.0530"},
        "methodology": "LightGCN Yelp2018 full-ranking split.",
    },
    {
        "paper_arxiv": "2110.15114",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "yelp2018-ngcf-lightgcn-full-ranking",
        "model_name": "UltraGCN",
        "metric": "Recall@20",
        "score": "0.0683",
        "extra": {"NDCG@20": "0.0561"},
        "methodology": "UltraGCN Yelp2018 source row on the LightGCN split.",
    },
    {
        "paper_arxiv": "2109.12613",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "yelp2018-ngcf-lightgcn-full-ranking",
        "model_name": "SimpleX",
        "metric": "Recall@20",
        "score": "0.0701",
        "extra": {"NDCG@20": "0.0575"},
        "methodology": "SimpleX Yelp2018 source row on the LightGCN split.",
    },
    {
        "paper_arxiv": "2211.09324",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "yelp2018-ngcf-lightgcn-full-ranking",
        "model_name": "BSPM-EM",
        "metric": "Recall@20",
        "score": "0.0720",
        "extra": {"NDCG@20": "0.0593"},
        "methodology": "BSPM Yelp2018 source row on the LightGCN split.",
    },
    {
        "paper_arxiv": "2402.11523",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "yelp2018-ngcf-lightgcn-full-ranking",
        "model_name": "NESCL",
        "metric": "Recall@20",
        "score": "0.0743",
        "extra": {"NDCG@20": "0.0611"},
        "methodology": "NESCL Yelp2018 source row on the LightGCN split.",
    },
    {
        "paper_arxiv": "1905.08108",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "amazon-book-ngcf-lightgcn-full-ranking",
        "model_name": "NGCF",
        "metric": "Recall@20",
        "score": "0.0344",
        "extra": {"NDCG@20": "0.0263"},
        "methodology": "NGCF/LightGCN Amazon-Book full-ranking split.",
    },
    {
        "paper_arxiv": "2002.02126",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "amazon-book-ngcf-lightgcn-full-ranking",
        "model_name": "LightGCN",
        "metric": "Recall@20",
        "score": "0.0411",
        "extra": {"NDCG@20": "0.0315"},
        "methodology": "LightGCN Amazon-Book full-ranking split.",
    },
    {
        "paper_arxiv": "2109.12613",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "amazon-book-ngcf-lightgcn-full-ranking",
        "model_name": "SimpleX",
        "metric": "Recall@20",
        "score": "0.0583",
        "extra": {"NDCG@20": "0.0468"},
        "methodology": "SimpleX Amazon-Book source row on the LightGCN split.",
    },
    {
        "paper_arxiv": "2211.09324",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "amazon-book-ngcf-lightgcn-full-ranking",
        "model_name": "BSPM-LM",
        "metric": "Recall@20",
        "score": "0.0733",
        "extra": {"NDCG@20": "0.0610"},
        "methodology": "BSPM Amazon-Book source row on the LightGCN split.",
    },
    {
        "paper_arxiv": "1708.05031",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "movielens-1m-ncf-100-negative-loo",
        "model_name": "NeuMF",
        "metric": "HR@10",
        "score": "0.730",
        "extra": {"NDCG@10": "0.447"},
        "methodology": "NCF MovieLens-1M leave-one-out protocol with 100 sampled negatives.",
    },
    {
        "paper_arxiv": "1708.05031",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "movielens-1m-ncf-100-negative-loo",
        "model_name": "GMF",
        "metric": "HR@10",
        "score": "0.689",
        "extra": {"NDCG@10": "0.418"},
        "methodology": "NCF paper MovieLens-1M leave-one-out protocol with 100 sampled negatives.",
    },
    {
        "paper_arxiv": "1708.05031",
        "task_slug": "collaborative-filtering",
        "dataset_slug": "movielens-1m-ncf-100-negative-loo",
        "model_name": "MLP",
        "metric": "HR@10",
        "score": "0.691",
        "extra": {"NDCG@10": "0.415"},
        "methodology": "NCF paper MovieLens-1M leave-one-out protocol with 100 sampled negatives.",
    },
    # Sequential and session.
    {
        "paper_arxiv": "1808.09781",
        "task_slug": "sequential-recommendation",
        "dataset_slug": "steam-sasrec-100-negative-sequential",
        "model_name": "SASRec",
        "metric": "Hit@10",
        "score": "0.8729",
        "extra": {"NDCG@10": "0.6306"},
        "methodology": "SASRec source row on Steam; chronological next-item evaluation with sampled negatives.",
    },
    {
        "paper_arxiv": "1808.09781",
        "task_slug": "sequential-recommendation",
        "dataset_slug": "amazon-beauty-sasrec-100-negative-sequential",
        "model_name": "SASRec",
        "metric": "Hit@10",
        "score": "0.4854",
        "extra": {"NDCG@10": "0.3219"},
        "methodology": "SASRec source row on Amazon Beauty sampled-negative next-item evaluation.",
    },
    {
        "paper_arxiv": "2204.06519",
        "task_slug": "sequential-recommendation",
        "dataset_slug": "amazon-beauty-sasrec-100-negative-sequential",
        "model_name": "CARCA",
        "metric": "Hit@10",
        "score": "0.5790",
        "extra": {"NDCG@10": "0.3960"},
        "methodology": "CARCA source row on Amazon Beauty sampled-negative sequential recommendation.",
    },
    {
        "paper_arxiv": "2312.06145",
        "task_slug": "sequential-recommendation",
        "dataset_slug": "amazon-beauty-sasrec-100-negative-sequential",
        "model_name": "ProxyRCA",
        "metric": "Hit@10",
        "score": "0.6260",
        "extra": {"NDCG@10": "0.4490"},
        "methodology": "ProxyRCA source row on Amazon Beauty sampled-negative sequential recommendation.",
    },
    {
        "paper_arxiv": "2405.10436",
        "task_slug": "sequential-recommendation",
        "dataset_slug": "amazon-beauty-sasrec-100-negative-sequential",
        "model_name": "CARCA Abs + Con",
        "metric": "Hit@10",
        "score": "0.6793",
        "extra": {},
        "methodology": "Positional-encoding study source row on Amazon Beauty; NDCG in legacy source used a non-cutoff label and is not imported here.",
    },
    {
        "paper_arxiv": "1808.09781",
        "task_slug": "sequential-recommendation",
        "dataset_slug": "amazon-games-sasrec-100-negative-sequential",
        "model_name": "SASRec",
        "metric": "Hit@10",
        "score": "0.7410",
        "extra": {"NDCG@10": "0.5360"},
        "methodology": "SASRec source row on Amazon Games sampled-negative next-item evaluation.",
    },
    {
        "paper_arxiv": "2204.06519",
        "task_slug": "sequential-recommendation",
        "dataset_slug": "amazon-games-sasrec-100-negative-sequential",
        "model_name": "CARCA",
        "metric": "Hit@10",
        "score": "0.7820",
        "extra": {"NDCG@10": "0.5730"},
        "methodology": "CARCA source row on Amazon Games sampled-negative sequential recommendation.",
    },
    {
        "paper_arxiv": "2312.06145",
        "task_slug": "sequential-recommendation",
        "dataset_slug": "amazon-games-sasrec-100-negative-sequential",
        "model_name": "ProxyRCA",
        "metric": "Hit@10",
        "score": "0.8090",
        "extra": {"NDCG@10": "0.6110"},
        "methodology": "ProxyRCA source row on Amazon Games sampled-negative sequential recommendation.",
    },
    {
        "paper_arxiv": "1811.00855",
        "task_slug": "session-based-recommendation",
        "dataset_slug": "yoochoose-1-64-srgnn-session",
        "model_name": "SR-GNN",
        "metric": "Precision@20",
        "score": "0.7090",
        "extra": {"MRR@20": "0.3094"},
        "methodology": "SR-GNN paper table; YOOCHOOSE 1/64 session split with Precision@20 and MRR@20.",
    },
    {
        "paper_arxiv": "1811.00855",
        "task_slug": "session-based-recommendation",
        "dataset_slug": "yoochoose-1-4-srgnn-session",
        "model_name": "SR-GNN",
        "metric": "Precision@20",
        "score": "0.7194",
        "extra": {"MRR@20": "0.3121"},
        "methodology": "SR-GNN paper table; YOOCHOOSE 1/4 session split with Precision@20 and MRR@20.",
    },
    {
        "paper_arxiv": "1811.00855",
        "task_slug": "session-based-recommendation",
        "dataset_slug": "diginetica-srgnn-session",
        "model_name": "SR-GNN",
        "metric": "Precision@20",
        "score": "0.5073",
        "extra": {"MRR@20": "0.1789"},
        "methodology": "SR-GNN paper table; Diginetica time-split session recommendation.",
    },
    {
        "paper_arxiv": "1711.04725",
        "task_slug": "session-based-recommendation",
        "dataset_slug": "yoochoose-1-64-srgnn-session",
        "model_name": "NARM",
        "metric": "Precision@20",
        "score": "0.6832",
        "extra": {"MRR@20": "0.2863"},
        "methodology": "NARM source paper table; YOOCHOOSE 1/64 session recommendation with Precision@20 and MRR@20.",
    },
    {
        "paper_arxiv": "1711.04725",
        "task_slug": "session-based-recommendation",
        "dataset_slug": "yoochoose-1-4-srgnn-session",
        "model_name": "NARM",
        "metric": "Precision@20",
        "score": "0.6973",
        "extra": {"MRR@20": "0.2923"},
        "methodology": "NARM source paper table; YOOCHOOSE 1/4 session recommendation with Precision@20 and MRR@20.",
    },
    {
        "paper_arxiv": "1711.04725",
        "task_slug": "session-based-recommendation",
        "dataset_slug": "diginetica-srgnn-session",
        "model_name": "NARM",
        "metric": "Precision@20",
        "score": "0.4970",
        "extra": {"MRR@20": "0.1617"},
        "methodology": "NARM source paper table; Diginetica session recommendation with Precision@20 and MRR@20.",
    },
    # CTR public protocol spine.
    {
        "paper_arxiv": "2304.00902",
        "task_slug": "click-through-rate-prediction",
        "dataset_slug": "criteo-dcnv2-ctr-protocol",
        "model_name": "FinalMLP",
        "metric": "AUC",
        "score": "0.8149",
        "extra": {},
        "methodology": "FinalMLP source row on Criteo public CTR protocol.",
    },
    {
        "paper_arxiv": "1606.07792",
        "task_slug": "click-through-rate-prediction",
        "dataset_slug": "criteo-dcnv2-ctr-protocol",
        "model_name": "Wide&Deep",
        "metric": "AUC",
        "score": "0.7981",
        "extra": {"Log Loss": "0.46772"},
        "methodology": "Wide & Deep source row on the public Criteo CTR protocol.",
    },
    {
        "paper_arxiv": "1703.04247",
        "task_slug": "click-through-rate-prediction",
        "dataset_slug": "criteo-dcnv2-ctr-protocol",
        "model_name": "DeepFM",
        "metric": "AUC",
        "score": "0.8007",
        "extra": {"Log Loss": "0.45083"},
        "methodology": "DeepFM source row on the public Criteo CTR protocol.",
    },
    {
        "paper_arxiv": "1803.05170",
        "task_slug": "click-through-rate-prediction",
        "dataset_slug": "criteo-dcnv2-ctr-protocol",
        "model_name": "xDeepFM",
        "metric": "AUC",
        "score": "0.8052",
        "extra": {"Log Loss": "0.4418"},
        "methodology": "xDeepFM source row on the public Criteo CTR protocol.",
    },
    {
        "paper_arxiv": "1810.11921",
        "task_slug": "click-through-rate-prediction",
        "dataset_slug": "criteo-dcnv2-ctr-protocol",
        "model_name": "AutoInt",
        "metric": "AUC",
        "score": "0.8061",
        "extra": {"Log Loss": "0.4454"},
        "methodology": "AutoInt source row on the public Criteo CTR protocol.",
    },
    {
        "paper_arxiv": "2008.13535",
        "task_slug": "click-through-rate-prediction",
        "dataset_slug": "criteo-dcnv2-ctr-protocol",
        "model_name": "DCNv2",
        "metric": "AUC",
        "score": "0.8115",
        "extra": {"Log Loss": "0.4406"},
        "methodology": "DCNv2 source row on the public Criteo CTR protocol.",
    },
    {
        "paper_arxiv": "2311.04635",
        "task_slug": "click-through-rate-prediction",
        "dataset_slug": "criteo-dcnv2-ctr-protocol",
        "model_name": "GDCN",
        "metric": "AUC",
        "score": "0.8161",
        "extra": {"Log Loss": "0.4360"},
        "methodology": "GDCN source row on the public Criteo CTR protocol.",
    },
    {
        "paper_arxiv": "2407.13349",
        "task_slug": "click-through-rate-prediction",
        "dataset_slug": "criteo-dcnv2-ctr-protocol",
        "model_name": "DCNv3",
        "metric": "AUC",
        "score": "0.8162",
        "extra": {"Log Loss": "0.4358"},
        "methodology": "DCNv3 source row on Criteo public CTR protocol.",
    },
    {
        "paper_arxiv": "1810.11921",
        "task_slug": "click-through-rate-prediction",
        "dataset_slug": "avazu-chronological-ctr",
        "model_name": "AutoInt",
        "metric": "AUC",
        "score": "0.7752",
        "extra": {"LogLoss": "0.3823"},
        "methodology": "AutoInt source row on Avazu chronological CTR protocol.",
    },
    {
        "paper_arxiv": "2108.01265",
        "task_slug": "click-through-rate-prediction",
        "dataset_slug": "avazu-chronological-ctr",
        "model_name": "OptInter",
        "metric": "AUC",
        "score": "0.8062",
        "extra": {"LogLoss": "0.3637"},
        "methodology": "OptInter source row on Avazu chronological CTR protocol.",
    },
    {
        "paper_arxiv": "2407.13349",
        "task_slug": "click-through-rate-prediction",
        "dataset_slug": "avazu-chronological-ctr",
        "model_name": "DCNv3",
        "metric": "AUC",
        "score": "0.7970",
        "extra": {"LogLoss": "0.3695"},
        "methodology": "DCNv3 source row on Avazu chronological CTR protocol.",
    },
    {
        "paper_arxiv": "1810.11921",
        "task_slug": "click-through-rate-prediction",
        "dataset_slug": "kdd12-autoint-ctr-protocol",
        "model_name": "AutoInt",
        "metric": "AUC",
        "score": "0.7881",
        "extra": {"Log Loss": "0.1545"},
        "methodology": "AutoInt source row on KDD12 CTR protocol.",
    },
    {
        "paper_arxiv": "2407.13349",
        "task_slug": "click-through-rate-prediction",
        "dataset_slug": "kdd12-autoint-ctr-protocol",
        "model_name": "DCNv3",
        "metric": "AUC",
        "score": "0.8098",
        "extra": {"Log Loss": "0.1494"},
        "methodology": "DCNv3 source row on KDD12 CTR protocol.",
    },
]

LEDGER = {
    "implemented": {
        "tasks": [task["slug"] for task in TASKS],
        "benchmarks": [bench["slug"] for bench in BENCHMARKS],
        "seed_eval_rows": len(EVALS),
    },
    "deferred_public_but_needs_exact_protocol": [
        "FuxiCTR/BARS Criteo_x1, Criteo_x2, Criteo_x4, Avazu_x1",
        "MovieLens-100K official folds and Netflix Prize explicit-rating pages",
        "Full-catalog S3-Rec/BERT4Rec variants where 99-negative and all-item protocols coexist",
        "P5, LETTER, HLLM, GRID detailed Amazon generative recommendation rows",
        "Yambda-500M/Yambda-5B and RecIF subset-specific rows",
        "MIND news recommendation child task",
        "Knowledge graph / multimodal recommendation variants such as KGAT, KGCN, LATTICE, FREEDOM",
    ],
    "industrial_or_private_evidence_only": [
        "OneRec 2502.18965 private production reward metrics",
        "Large-scale Generative Ranking 2505.04180 private ranking data",
        "RankMixer 2507.15551 industrial ranking",
        "Generative CTR 2507.11246 private deployment tables",
        "OneTrans 2510.26104 private industrial AUC/UAUC",
        "LLaTTE 2601.20083 private ads scaling laws",
        "OneReason 2606.06260 unreleased 8B system scores",
        "LoopCTR 2604.19550 private loop-scaling CTR tables until public protocols are pinned down",
    ],
    "verification_notes": [
        "LTR pages are benchmark contracts only in this pass; no framework README reruns were imported.",
        "Session recommendation rows use source-paper SR-GNN table values, not later comparison-table baselines.",
        "CTR private Company* and online A/B-test rows from legacy PwC were not imported.",
        "Text passage ranking and neural retrieval/reranking rows were left under retrieval-oriented tasks.",
    ],
}
