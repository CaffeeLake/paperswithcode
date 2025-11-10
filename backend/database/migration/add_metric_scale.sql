-- Migration: Add scale column to metrics table
-- Purpose: Track the canonical scale for each metric (e.g., "0-1" for AbsRel, "0-100" for mIoU)
-- Date: 2025-11-10
-- This helps AI agents normalize metric values to the correct scale during evaluation extraction

-- Add scale column to metrics table
ALTER TABLE metrics ADD COLUMN IF NOT EXISTS scale VARCHAR(50);

-- Add comment explaining the scale column
COMMENT ON COLUMN metrics.scale IS 'Canonical scale for metric values. Examples: "0-1" for ratios/decimals, "0-100" for percentages, "milliseconds" for time-based metrics';

-- Update some common metrics with their canonical scales
-- These are the most commonly used scales; more can be added as needed

-- Percentage-based metrics (0-100 scale)
UPDATE metrics SET scale = '0-100' WHERE name IN (
    'mIoU', 'Top-1 Accuracy', 'Top-5 Accuracy', 'Accuracy',
    'Precision', 'Recall', 'F1'
) AND scale IS NULL;

-- Ratio/decimal metrics (0-1 scale)
UPDATE metrics SET scale = '0-1' WHERE name IN (
    'IoU', 'Dice', 'AUC'
) AND scale IS NULL;

-- Detection metrics (0-100 scale, typically reported as percentages)
UPDATE metrics SET scale = '0-100' WHERE name IN (
    'mAP', 'AP', 'AP50', 'AP75', 'APS', 'APM', 'APL', 'box AP'
) AND scale IS NULL;

-- NLG metrics (0-100 scale)
UPDATE metrics SET scale = '0-100' WHERE name IN (
    'BLEU', 'ROUGE', 'ROUGE-L', 'METEOR'
) AND scale IS NULL;

-- Error metrics (0-1 scale for ratios, 0-100 for percentages)
-- Note: WER and CER are typically reported as percentages (0-100)
UPDATE metrics SET scale = '0-100' WHERE name IN (
    'WER', 'CER', 'Error Rate'
) AND scale IS NULL;

-- Depth estimation metrics (0-1 scale for error ratios)
UPDATE metrics SET scale = '0-1' WHERE name IN (
    'AbsRel', 'SqRel', 'RMSE', 'RMSElog'
) AND scale IS NULL;

-- Depth accuracy metrics (0-1 scale for thresholds like delta1, delta2, delta3)
UPDATE metrics SET scale = '0-1' WHERE name IN (
    'delta1', 'delta2', 'delta3'
) AND scale IS NULL;

-- Loss/error metrics (typically unbounded or context-dependent)
UPDATE metrics SET scale = 'unbounded' WHERE name IN (
    'Loss', 'MAE', 'MSE', 'FID', 'Perplexity'
) AND scale IS NULL;
