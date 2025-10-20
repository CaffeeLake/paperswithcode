-- Migration: Create metrics table for storing metric definitions with ranking direction
-- Purpose: Support both "higher is better" (AP, accuracy) and "lower is better" (WER, error rates) metrics
-- Date: 2025-10-19

-- Create metrics table
CREATE TABLE IF NOT EXISTS metrics (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    direction VARCHAR(20) NOT NULL CHECK (direction IN ('higher_is_better', 'lower_is_better')),
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index for fast lookups
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name);

-- Insert common metrics with their ranking directions

-- Lower is better metrics (error rates, perplexity)
INSERT INTO metrics (name, full_name, direction, description) VALUES
    ('WER', 'Word Error Rate', 'lower_is_better', 'Word Error Rate - commonly used in speech recognition evaluation'),
    ('CER', 'Character Error Rate', 'lower_is_better', 'Character Error Rate - used in speech recognition and OCR'),
    ('Perplexity', 'Perplexity', 'lower_is_better', 'Language model perplexity - lower indicates better model fit'),
    ('Error Rate', 'Error Rate', 'lower_is_better', 'General error rate metric'),
    ('Loss', 'Loss', 'lower_is_better', 'Training or validation loss'),
    ('MAE', 'Mean Absolute Error', 'lower_is_better', 'Mean Absolute Error'),
    ('MSE', 'Mean Squared Error', 'lower_is_better', 'Mean Squared Error'),
    ('RMSE', 'Root Mean Squared Error', 'lower_is_better', 'Root Mean Squared Error'),
    ('FID', 'Frechet Inception Distance', 'lower_is_better', 'Image generation quality metric')
ON CONFLICT (name) DO NOTHING;

-- Higher is better metrics (accuracy, precision, recall, F1, etc.)
INSERT INTO metrics (name, full_name, direction, description) VALUES
    ('AP', 'Average Precision', 'higher_is_better', 'Average Precision - object detection metric'),
    ('mAP', 'Mean Average Precision', 'higher_is_better', 'Mean Average Precision across classes'),
    ('box AP', 'Box Average Precision', 'higher_is_better', 'Bounding box Average Precision for object detection'),
    ('AP50', 'AP at IoU=0.50', 'higher_is_better', 'Average Precision at 50% IoU threshold'),
    ('AP75', 'AP at IoU=0.75', 'higher_is_better', 'Average Precision at 75% IoU threshold'),
    ('APS', 'AP Small', 'higher_is_better', 'Average Precision for small objects'),
    ('APM', 'AP Medium', 'higher_is_better', 'Average Precision for medium objects'),
    ('APL', 'AP Large', 'higher_is_better', 'Average Precision for large objects'),
    ('Accuracy', 'Accuracy', 'higher_is_better', 'Classification accuracy'),
    ('Top-1 Accuracy', 'Top-1 Accuracy', 'higher_is_better', 'Top-1 classification accuracy'),
    ('Top-5 Accuracy', 'Top-5 Accuracy', 'higher_is_better', 'Top-5 classification accuracy'),
    ('F1', 'F1 Score', 'higher_is_better', 'Harmonic mean of precision and recall'),
    ('Precision', 'Precision', 'higher_is_better', 'Precision score'),
    ('Recall', 'Recall', 'higher_is_better', 'Recall score'),
    ('AUC', 'Area Under Curve', 'higher_is_better', 'Area Under ROC Curve'),
    ('BLEU', 'BLEU Score', 'higher_is_better', 'Bilingual Evaluation Understudy for translation'),
    ('ROUGE', 'ROUGE Score', 'higher_is_better', 'Recall-Oriented Understudy for Gisting Evaluation'),
    ('ROUGE-L', 'ROUGE-L', 'higher_is_better', 'ROUGE Longest Common Subsequence'),
    ('METEOR', 'METEOR', 'higher_is_better', 'Metric for Evaluation of Translation with Explicit ORdering'),
    ('IoU', 'Intersection over Union', 'higher_is_better', 'Intersection over Union for object detection/segmentation'),
    ('Dice', 'Dice Coefficient', 'higher_is_better', 'Dice coefficient for segmentation'),
    ('mIoU', 'Mean IoU', 'higher_is_better', 'Mean Intersection over Union'),
    ('R@1', 'Recall at 1', 'higher_is_better', 'Recall at top-1'),
    ('R@5', 'Recall at 5', 'higher_is_better', 'Recall at top-5'),
    ('R@10', 'Recall at 10', 'higher_is_better', 'Recall at top-10'),
    ('MRR', 'Mean Reciprocal Rank', 'higher_is_better', 'Mean Reciprocal Rank for ranking tasks'),
    ('NDCG', 'Normalized Discounted Cumulative Gain', 'higher_is_better', 'Normalized Discounted Cumulative Gain for ranking'),
    ('PSNR', 'Peak Signal-to-Noise Ratio', 'higher_is_better', 'Peak Signal-to-Noise Ratio for image quality')
ON CONFLICT (name) DO NOTHING;

-- Log successful migration
DO $$
BEGIN
    RAISE NOTICE 'Metrics table created successfully with % metric definitions', (SELECT COUNT(*) FROM metrics);
END $$;
