UPDATE methods
SET
    image_url = 'https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/blog/moe/01_moe_layer.png',
    image_credit = '[Hugging Face MoE blog](https://huggingface.co/blog/moe)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug IN ('mixture-of-experts', 'moe');
