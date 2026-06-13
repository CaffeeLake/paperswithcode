-- Add RNN-Transducer (RNN-T) method.
-- Source paper: arXiv 1211.3711

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
    'rnn-transducer',
    'RNN-Transducer',
    'Recurrent Neural Network Transducer (RNN-T)',
    'The RNN-Transducer (RNN-T) is an end-to-end sequence transduction model that combines a transcription network over the input, a prediction network over previous outputs, and a joint network that scores label emissions at each alignment step. Unlike CTC, it models output-output dependencies, so it can generate output sequences longer than the input and became a standard decoder for streaming speech recognition. Modern ASR systems often pair RNN-T with [Conformer](/methods/conformer) or other encoders.',
    'RNN-Transducer, RNN-T, RNNT, rnn transducer, recurrent neural network transducer, sequence transducer',
    (
        SELECT id
        FROM areas
        WHERE name = 'Audio'
        LIMIT 1
    ),
    2012,
    (
        SELECT id
        FROM papers
        WHERE arxiv_id = '1211.3711'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Sequence Transduction with Recurrent Neural Networks',
    'https://github.com/pytorch/audio/blob/main/torchaudio/models/rnnt.py',
    'https://paperswithcode.co/images/methods/rnn-transducer.png',
    '[Sequence Transduction with Recurrent Neural Networks](/paper/1211.3711)'
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
WHERE slug = 'rnn-transducer'
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;
