UPDATE tasks
SET keywords = 'mathematical reasoning, math reasoning, mathematical problem solving, math problem solving, AIME, USAMO, gsm8k, MATH benchmark, MATH dataset, math 500, math-500, AMO-Bench, AnswerBench, FrontierScience-Olympiad, FrontierScience-Research, HiddenMath, HMMT Feb 2025, HMMT Feb 2026, IMO 2025, IMO-ProofBench, IPhO 2024, IPhO 2025, MathVerse, MGSM, Minerva Math, OlympiadBench',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'math';
