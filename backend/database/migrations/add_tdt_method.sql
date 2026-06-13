-- Add Token-and-Duration Transducer (TDT) method.
-- Source paper: arXiv 2304.06795

INSERT INTO methods (
    slug,
    name,
    full_name,
    description,
    keywords,
    area_id,
    introduced_year,
    source_paper_id,
    source_url,
    source_title,
    code_snippet_url,
    image_url,
    image_credit
)
VALUES (
    'tdt',
    'TDT',
    'Token-and-Duration Transducer (TDT)',
    'The Token-and-Duration Transducer (TDT) extends the [RNN-Transducer](/methods/rnn-transducer) by having the joint network predict both the next token and how many encoder frames that token covers. At inference time, the predicted duration lets decoding skip input frames instead of advancing one step at a time, making TDT up to about 2.8× faster than a standard transducer while matching or improving accuracy on ASR, speech translation, and spoken language understanding.',
    'TDT, Token-and-Duration Transducer, token and duration transducer, token-duration transducer, duration transducer',
    (
        SELECT id
        FROM areas
        WHERE name = 'Audio'
        LIMIT 1
    ),
    2023,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '2304.06795'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Efficient Sequence Transduction by Jointly Predicting Tokens and Durations',
    'https://github.com/NVIDIA/NeMo/blob/main/nemo/collections/asr/losses/tdt_loss.py',
    'https://paperswithcode.co/images/methods/tdt.png',
    '[Efficient Sequence Transduction by Jointly Predicting Tokens and Durations](/paper/2304.06795)'
)
ON CONFLICT (slug) DO UPDATE
SET
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
SELECT source_paper_id, id
FROM methods
WHERE slug = 'tdt'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
