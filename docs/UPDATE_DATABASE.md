You can use a query similar to this one to update database records:

```bash
PGPASSWORD=paperswithcode123 psql -h localhost -U paperswithcode_user -d paperswithcode_hf -c \
"UPDATE methods SET image_url = 'YOUR_IMAGE_URL_HERE' WHERE name ILIKE 'function calling';"
```

or directly in a SQL client:

```bash
UPDATE methods
SET image_url = 'https://example.com/image.png',
    image_credit = 'Source: Original Paper (https://arxiv.org/...)'
WHERE name ILIKE 'function calling';
```
