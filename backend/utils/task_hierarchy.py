"""
Task hierarchy helpers.

Subtasks are modelled as child rows in the `tasks` table via
`tasks.parent_id`. These helpers walk the hierarchy when an API caller asks
for parent rollups, e.g. "give me every benchmark under Language Modeling
including its subtasks".
"""

from typing import List

from sqlalchemy import text
from sqlalchemy.orm import Session


def collect_descendant_task_ids(db: Session, task_id: int) -> List[int]:
    """Return `task_id` plus every descendant task id reachable via parent_id.

    Uses a recursive CTE so depth is bounded by the database, not Python
    recursion. The returned list always contains `task_id` first.
    """
    rows = db.execute(
        text(
            """
            WITH RECURSIVE descendants(id) AS (
                SELECT id FROM tasks WHERE id = :task_id
                UNION ALL
                SELECT t.id FROM tasks t
                JOIN descendants d ON t.parent_id = d.id
            )
            SELECT id FROM descendants
            """
        ),
        {"task_id": task_id},
    ).all()
    return [row[0] for row in rows]
