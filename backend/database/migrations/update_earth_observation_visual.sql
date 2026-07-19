-- Earth Observation task hero: OlmoEarth global training-data coverage map.
UPDATE tasks
SET
    image_url = NULL,
    image_credit = '[OlmoEarth: A new state-of-the-art Earth observation foundation model family](https://allenai.org/blog/olmoearth-models)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'earth-observation';
