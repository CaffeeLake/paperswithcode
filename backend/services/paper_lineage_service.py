"""Rule-based management of directed predecessor/successor paper links."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.database import Paper, PaperRelation
from backend.utils.paper_reference import resolve_paper


@dataclass(frozen=True)
class LineagePaper:
    id: int
    reference: str
    title: str

    @classmethod
    def from_paper(cls, paper: Paper, reference: str) -> "LineagePaper":
        return cls(id=paper.id, reference=reference, title=paper.title)

    def to_dict(self) -> dict:
        return {"id": self.id, "reference": self.reference, "title": self.title}


@dataclass(frozen=True)
class LineageEdge:
    predecessor: LineagePaper
    successor: LineagePaper
    status: str

    def to_dict(self) -> dict:
        return {
            "predecessor": self.predecessor.to_dict(),
            "successor": self.successor.to_dict(),
            "status": self.status,
        }


@dataclass(frozen=True)
class PaperLineage:
    paper: LineagePaper
    predecessors: tuple[LineagePaper, ...]
    successors: tuple[LineagePaper, ...]

    def to_dict(self) -> dict:
        return {
            "paper": self.paper.to_dict(),
            "predecessors": [paper.to_dict() for paper in self.predecessors],
            "successors": [paper.to_dict() for paper in self.successors],
        }


def _resolve(db: Session, reference: str) -> LineagePaper:
    paper, route_reference = resolve_paper(db, reference)
    return LineagePaper.from_paper(paper, route_reference)


def add_lineage_chain(
    db: Session, references: Sequence[str]
) -> tuple[LineageEdge, ...]:
    """Add each adjacent predecessor -> successor edge in a paper chain."""
    if len(references) < 2:
        raise ValueError("A lineage chain requires at least two papers")

    papers = [_resolve(db, reference) for reference in references]
    if len({paper.id for paper in papers}) != len(papers):
        raise ValueError("A lineage chain cannot contain the same paper twice")

    edges = []
    for predecessor, successor in zip(papers, papers[1:]):
        relation = db.get(PaperRelation, (predecessor.id, successor.id))
        status = "existing" if relation else "created"
        if relation is None:
            db.add(
                PaperRelation(
                    source_paper_id=predecessor.id,
                    target_paper_id=successor.id,
                )
            )
        edges.append(LineageEdge(predecessor, successor, status))

    db.commit()
    return tuple(edges)


def remove_lineage_edge(
    db: Session,
    predecessor_reference: str,
    successor_reference: str,
) -> LineageEdge:
    predecessor = _resolve(db, predecessor_reference)
    successor = _resolve(db, successor_reference)
    relation = db.get(PaperRelation, (predecessor.id, successor.id))
    if relation is None:
        status = "not_found"
    else:
        db.delete(relation)
        db.commit()
        status = "removed"
    return LineageEdge(predecessor, successor, status)


def get_paper_lineage(db: Session, reference: str) -> PaperLineage:
    paper = _resolve(db, reference)
    predecessor_rows = db.execute(
        select(Paper)
        .join(PaperRelation, Paper.id == PaperRelation.source_paper_id)
        .where(PaperRelation.target_paper_id == paper.id)
        .order_by(Paper.date_published, Paper.id)
    ).scalars()
    successor_rows = db.execute(
        select(Paper)
        .join(PaperRelation, Paper.id == PaperRelation.target_paper_id)
        .where(PaperRelation.source_paper_id == paper.id)
        .order_by(Paper.date_published, Paper.id)
    ).scalars()

    def summarize(rows) -> tuple[LineagePaper, ...]:
        return tuple(
            LineagePaper.from_paper(row, row.arxiv_id or str(row.id)) for row in rows
        )

    return PaperLineage(
        paper=paper,
        predecessors=summarize(predecessor_rows),
        successors=summarize(successor_rows),
    )
