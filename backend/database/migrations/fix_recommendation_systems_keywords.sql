-- Remove the ambiguous standalone "recommendation" keyword. It tagged papers
-- that merely made recommendations rather than studying recommender systems.
UPDATE tasks
SET keywords = 'recommender, recommender system, recommendation system, personalized recommendation, collaborative filtering, item recommendation, product recommendation, content recommendation, recommendation engine, top-N recommendation, implicit feedback, explicit feedback, sequential recommendation, session recommendation, click-through rate prediction, CTR prediction, learning to rank, ranking model, generative recommendation, semantic ID, industrial recommendation',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'recommendation-systems';
