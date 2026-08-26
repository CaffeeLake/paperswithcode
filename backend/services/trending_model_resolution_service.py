"""Apply one validated trending-model paper resolution transaction."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.models.api import ResolveModelPaperMutation
from backend.models.database import (
    Evaluation,
    HfArtifact,
    ModelProviderAlias,
    ModelRelease,
    ModelReleaseArtifact,
    Paper,
    PaperAuthor,
    PaperConference,
    PaperDataset,
    PaperHfArtifact,
    PaperMethod,
    PaperMethodEvidence,
    PaperMethodExclusion,
    PaperOrganization,
    PaperProjectPage,
    PaperRepository,
    PaperTask,
    ProjectPage,
    TrendingModelCandidate,
)
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.paper_ingestion_service import PaperIngestionService


class TrendingModelResolutionService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def apply(
        self,
        candidate_id: uuid.UUID,
        mutation: ResolveModelPaperMutation,
        *,
        commit: bool = True,
    ) -> dict:
        candidate = self.db.get(TrendingModelCandidate, candidate_id)
        if candidate is None:
            raise LookupError("Trending model candidate not found")
        if candidate.status not in {"queued", "resolving"}:
            raise RuntimeError("Trending model candidate is not accepting a resolution")

        if mutation.decision == "reject":
            candidate.status = "rejected"
            candidate.rejection_reason = mutation.reason
            candidate.processed_at = datetime.now(UTC)
            if commit:
                self.db.commit()
            else:
                self.db.flush()
            return {"status": "rejected", "candidate_id": str(candidate.id)}

        paper = self._resolve_paper(mutation, candidate)
        proposal = mutation.model_release
        assert proposal is not None
        release = self._find_release(candidate, paper, proposal)
        if (
            release is not None
            and release.paper_id != paper.id
            and paper.source == "arxiv"
        ):
            previous = self.db.get(Paper, release.paper_id)
            if previous is not None and previous.source == "external":
                self._upgrade_external_paper(previous, paper)
        if release is not None:
            duplicate = (
                self.db.query(ModelRelease)
                .filter(
                    ModelRelease.paper_id == paper.id,
                    ModelRelease.canonical_name == proposal.canonical_name,
                    ModelRelease.id != release.id,
                )
                .one_or_none()
            )
            if duplicate is not None:
                self._merge_release_into(duplicate, release)
        if release is None:
            release = ModelRelease(
                paper_id=paper.id,
                canonical_name=proposal.canonical_name,
                publisher=proposal.publisher,
                canonical_source_url=self._canonical_paper_url(paper),
                aliases=proposal.aliases,
                is_open=proposal.is_open,
            )
            self.db.add(release)
            self.db.flush()
        else:
            # A model card may gain an arXiv report after its initial external
            # release page was curated. Preserve the release identity and move
            # its canonical paper pointer forward.
            release.paper_id = paper.id
            release.canonical_name = proposal.canonical_name
            release.publisher = proposal.publisher
            release.canonical_source_url = self._canonical_paper_url(paper)
            release.aliases = list(
                dict.fromkeys([*(release.aliases or []), *proposal.aliases])
            )
            release.is_open = proposal.is_open

        artifact = (
            self.db.query(HfArtifact)
            .filter(HfArtifact.kind == "model", HfArtifact.repo_id == candidate.repo_id)
            .one_or_none()
        )
        model_url = f"https://huggingface.co/{candidate.repo_id}"
        if artifact is None:
            artifact = HfArtifact(
                kind="model", repo_id=candidate.repo_id, url=model_url
            )
            self.db.add(artifact)
            self.db.flush()
        if self.db.get(PaperHfArtifact, (paper.id, artifact.id)) is None:
            self.db.add(PaperHfArtifact(paper_id=paper.id, hf_artifact_id=artifact.id))
        if (
            self.db.query(ModelReleaseArtifact)
            .filter(
                ModelReleaseArtifact.model_release_id == release.id,
                ModelReleaseArtifact.hf_artifact_id == artifact.id,
            )
            .one_or_none()
            is None
        ):
            self.db.add(
                ModelReleaseArtifact(
                    model_release_id=release.id, hf_artifact_id=artifact.id
                )
            )
        paper.hf_models = list(dict.fromkeys([*(paper.hf_models or []), model_url]))
        candidate.status = "resolved"
        candidate.rejection_reason = None
        candidate.model_release_id = release.id
        candidate.processed_at = datetime.now(UTC)
        if commit:
            self.db.commit()
        else:
            self.db.flush()
        return {
            "status": "resolved",
            "candidate_id": str(candidate.id),
            "paper_id": int(paper.id),
            "model_release_id": int(release.id),
        }

    def _resolve_paper(
        self, mutation: ResolveModelPaperMutation, candidate: TrendingModelCandidate
    ) -> Paper:
        if mutation.existing_paper_id is not None:
            paper = self.db.get(Paper, mutation.existing_paper_id)
            if paper is None:
                raise LookupError("Resolved paper not found")
            evidence = {url.rstrip("/") for url in mutation.evidence_urls}
            source_url = paper.source_url.rstrip("/") if paper.source_url else None
            source_supported = bool(
                source_url
                and (
                    source_url in evidence
                    or (
                        source_url.startswith("https://huggingface.co/")
                        and any(
                            url.startswith(f"{source_url}/raw/")
                            and url.endswith("/README.md")
                            for url in evidence
                        )
                    )
                )
            )
            arxiv_supported = bool(
                paper.arxiv_id
                and any(
                    f"/{paper.arxiv_id}" in url
                    or f"arxiv:{paper.arxiv_id}" in url.lower()
                    for url in evidence
                )
            )
            if not source_supported and not arxiv_supported:
                raise ValueError(
                    "Existing paper resolution requires canonical source evidence"
                )
            return paper
        if mutation.arxiv_id is not None:
            if not any(
                f"/{mutation.arxiv_id}" in url
                or f"arxiv:{mutation.arxiv_id}" in url.lower()
                for url in mutation.evidence_urls
            ):
                raise ValueError("arXiv resolution requires matching source evidence")
            paper, _ = asyncio.run(
                PaperIngestionService(self.db).get_or_import_arxiv_paper(
                    mutation.arxiv_id, commit=False
                )
            )
            return paper
        external = mutation.external_paper
        assert external is not None
        if external.source_url.rstrip("/") not in {
            url.rstrip("/") for url in mutation.evidence_urls
        }:
            raise ValueError(
                "External paper resolution requires matching source evidence"
            )
        result = ExternalResourceService(self.db).add_external_resource(
            ExternalResourceInput(
                source_url=external.source_url,
                title=external.title,
                abstract=external.abstract,
                date_published=external.date_published,
                hf_artifact_urls=[f"https://huggingface.co/{candidate.repo_id}"],
            ),
            commit=False,
        )
        paper = self.db.get(Paper, int(result.paper.id))
        if paper is None:
            raise RuntimeError("External paper ingestion returned no database row")
        return paper

    def _find_release(self, candidate, paper, proposal) -> ModelRelease | None:
        if candidate.model_release_id is not None:
            release = self.db.get(ModelRelease, candidate.model_release_id)
            if release is not None:
                return release
        release = (
            self.db.query(ModelRelease)
            .join(
                ModelReleaseArtifact,
                ModelReleaseArtifact.model_release_id == ModelRelease.id,
            )
            .join(HfArtifact, HfArtifact.id == ModelReleaseArtifact.hf_artifact_id)
            .filter(HfArtifact.kind == "model", HfArtifact.repo_id == candidate.repo_id)
            .one_or_none()
        )
        if release is not None:
            return release

        proposed_keys = self._identity_keys(
            proposal.canonical_name, *proposal.aliases, candidate.repo_id
        )
        releases = (
            self.db.query(ModelRelease)
            .filter(ModelRelease.paper_id == paper.id)
            .order_by(ModelRelease.id)
            .limit(100)
            .all()
        )
        matches = [
            release
            for release in releases
            if proposed_keys
            & self._identity_keys(release.canonical_name, *(release.aliases or []))
        ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _identity_keys(*values: str) -> set[str]:
        return {
            re.sub(r"[^a-z0-9]+", "", value.casefold())
            for value in values
            if value and re.sub(r"[^a-z0-9]+", "", value.casefold())
        }

    @staticmethod
    def _canonical_paper_url(paper: Paper) -> str | None:
        if paper.arxiv_id:
            return f"https://arxiv.org/abs/{paper.arxiv_id}"
        return paper.source_url

    def _upgrade_external_paper(self, source: Paper, target: Paper) -> None:
        """Move public curation from an external release onto its later arXiv paper."""
        for field in ("tldr", "thumbnail_url"):
            if getattr(target, field) is None:
                setattr(target, field, getattr(source, field))
        for field in ("hf_models", "hf_datasets", "hf_spaces"):
            setattr(
                target,
                field,
                list(
                    dict.fromkeys(
                        [
                            *(getattr(target, field) or []),
                            *(getattr(source, field) or []),
                        ]
                    )
                )
                or None,
            )

        if source.source_url:
            page = (
                self.db.query(ProjectPage)
                .filter(ProjectPage.url == source.source_url)
                .one_or_none()
            )
            if page is None:
                page = ProjectPage(
                    url=source.source_url,
                    is_official=True,
                    source="model-release-upgrade",
                )
                self.db.add(page)
                self.db.flush()
            if self.db.get(PaperProjectPage, (target.id, page.id)) is None:
                self.db.add(
                    PaperProjectPage(paper_id=target.id, project_page_id=page.id)
                )

        junctions = (
            PaperAuthor,
            PaperTask,
            PaperMethod,
            PaperMethodEvidence,
            PaperMethodExclusion,
            PaperDataset,
            PaperRepository,
            PaperProjectPage,
            PaperConference,
            PaperOrganization,
            PaperHfArtifact,
        )
        for model in junctions:
            for row in self.db.query(model).filter(model.paper_id == source.id).all():
                key = tuple(
                    target.id
                    if column.name == "paper_id"
                    else getattr(row, column.name)
                    for column in model.__table__.primary_key.columns
                )
                existing = self.db.get(model, key)
                if existing is not None:
                    if isinstance(row, PaperTask) and row.source == "manual":
                        existing.source = "manual"
                    elif isinstance(row, PaperRepository):
                        existing.is_official = bool(
                            existing.is_official or row.is_official
                        )
                    elif isinstance(row, PaperAuthor):
                        existing.author_order = min(
                            existing.author_order, row.author_order
                        )
                    self.db.delete(row)
                else:
                    row.paper_id = target.id

        self.db.query(Evaluation).filter(Evaluation.paper_id == source.id).update(
            {Evaluation.paper_id: target.id}, synchronize_session=False
        )
        releases = (
            self.db.query(ModelRelease)
            .filter(ModelRelease.paper_id == source.id)
            .order_by(ModelRelease.id)
            .all()
        )
        for release in releases:
            duplicate = (
                self.db.query(ModelRelease)
                .filter(
                    ModelRelease.paper_id == target.id,
                    ModelRelease.canonical_name == release.canonical_name,
                    ModelRelease.id != release.id,
                )
                .one_or_none()
            )
            if duplicate is not None:
                self._merge_release_into(duplicate, release)
            release.paper_id = target.id
            release.canonical_source_url = self._canonical_paper_url(target)
        source.is_latest_version = False

    def _merge_release_into(self, source: ModelRelease, target: ModelRelease) -> None:
        for link in (
            self.db.query(ModelReleaseArtifact)
            .filter(ModelReleaseArtifact.model_release_id == source.id)
            .all()
        ):
            existing = (
                self.db.query(ModelReleaseArtifact.id)
                .filter(
                    ModelReleaseArtifact.model_release_id == target.id,
                    ModelReleaseArtifact.hf_artifact_id == link.hf_artifact_id,
                )
                .first()
            )
            if existing:
                self.db.delete(link)
            else:
                link.model_release_id = target.id
        for alias in (
            self.db.query(ModelProviderAlias)
            .filter(ModelProviderAlias.model_release_id == source.id)
            .all()
        ):
            alias.model_release_id = target.id
        self.db.query(TrendingModelCandidate).filter(
            TrendingModelCandidate.model_release_id == source.id
        ).update(
            {TrendingModelCandidate.model_release_id: target.id},
            synchronize_session=False,
        )
        target.aliases = list(
            dict.fromkeys([*(target.aliases or []), *(source.aliases or [])])
        )
        self.db.delete(source)
        self.db.flush()
