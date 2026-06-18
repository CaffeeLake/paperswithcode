-- Drop architecture/pretraining keywords that fire on cross-domain citations
-- (e.g. audio papers mentioning ViT or ImageNet pretraining baselines).
UPDATE tasks
SET keywords = 'image classification, CIFAR10, CIFAR-10, imagenet, ILSVRC, CIFAR-100, VTAB'
WHERE slug = 'image-classification';
