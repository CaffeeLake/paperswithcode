-- Drop architecture/pretraining keywords that fire on cross-domain citations
-- (e.g. audio papers mentioning ViT or ImageNet pretraining baselines).
-- Do not keyword-match bare "ImageNet": generation/detection/VLM papers cite it
-- as a benchmark or pretraining corpus without being image-classification work.
UPDATE tasks
SET keywords = 'image classification, CIFAR10, CIFAR-10, ILSVRC, CIFAR-100, VTAB'
WHERE slug = 'image-classification';
