UPDATE datasets SET slug = 'flickr30k-image-to-text' WHERE slug IN ('flickr30k', 'flickr30k-image-to-text-retrieval');
UPDATE datasets SET slug = 'flickr30k-text-to-image' WHERE slug IN ('flickr30k-text-retrieval', 'flickr30k-text-to-image-retrieval');
UPDATE datasets SET slug = 'coco-captions-image-to-text' WHERE slug IN ('coco-captions', 'coco-captions-image-to-text-retrieval');
UPDATE datasets SET slug = 'coco-captions-text-to-image' WHERE slug IN ('coco-captions-text-retrieval', 'coco-captions-text-to-image-retrieval');
