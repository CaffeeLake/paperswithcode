"""Copy paper artifacts into a user's Hugging Face Bucket."""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError


BUCKET_OAUTH_COOKIE_NAME = "pwc_hf_bucket"
BUCKET_MANAGE_OAUTH_COOKIE_NAME = "pwc_hf_bucket_manage"
MAX_PDF_BYTES = 100 * 1024 * 1024
_REPO_ID_RE = re.compile(r"^[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*$")
_ARXIV_PDF_HOSTS = {"arxiv.org", "export.arxiv.org"}


def _configure_hugging_face_cache() -> None:
    runtime_data_dir = os.getenv("PWC_RUNTIME_DATA_DIR")
    if not runtime_data_dir:
        return
    hf_cache_dir = Path(runtime_data_dir) / "hf-cache"
    os.environ.setdefault("HF_HOME", str(hf_cache_dir))
    os.environ.setdefault("HF_XET_CACHE", str(hf_cache_dir / "xet"))


_configure_hugging_face_cache()


class PaperBucketError(ValueError):
    """A user-safe Bucket copy failure."""

    def __init__(self, message: str, *, authorization_required: bool = False):
        super().__init__(message)
        self.authorization_required = authorization_required


@dataclass(frozen=True)
class HubArtifact:
    kind: str
    repo_id: str

    @property
    def source(self) -> str:
        prefix = "" if self.kind == "model" else f"{self.kind}s/"
        return f"hf://{prefix}{self.repo_id}/"

    @property
    def destination(self) -> str:
        return f"{self.kind}s/{self.repo_id}/"

    @property
    def identifier(self) -> str:
        return f"{self.kind}:{self.repo_id}"


@dataclass(frozen=True)
class PaperBucketCopyResult:
    copied: tuple[str, ...]
    errors: tuple[tuple[str, str], ...]


def _hub_error(error: HfHubHTTPError) -> PaperBucketError:
    status_code = error.response.status_code if error.response is not None else None
    if status_code == 401:
        return PaperBucketError(
            "Hugging Face authorization is missing or no longer valid.",
            authorization_required=True,
        )
    if status_code == 403:
        return PaperBucketError(
            "Your Hugging Face account does not have permission for this Bucket operation."
        )
    return PaperBucketError("Hugging Face could not complete the Bucket operation.")


def _download_arxiv_pdf(url: str, destination: Path) -> None:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() not in _ARXIV_PDF_HOSTS
    ):
        raise PaperBucketError(
            "Only arXiv-hosted paper PDFs can be copied automatically."
        )

    try:
        with httpx.Client(
            timeout=httpx.Timeout(60, connect=10),
            follow_redirects=False,
            headers={"User-Agent": "paperswithcode.co paper bucket copy"},
        ) as client:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > MAX_PDF_BYTES:
                    raise PaperBucketError(
                        "The paper PDF exceeds the 100 MB copy limit."
                    )
                total = 0
                with destination.open("wb") as output:
                    for chunk in response.iter_bytes():
                        total += len(chunk)
                        if total > MAX_PDF_BYTES:
                            raise PaperBucketError(
                                "The paper PDF exceeds the 100 MB copy limit."
                            )
                        output.write(chunk)
                if total == 0:
                    raise PaperBucketError("The paper PDF download was empty.")
    except PaperBucketError:
        raise
    except (httpx.HTTPError, ValueError) as error:
        raise PaperBucketError(
            "The paper PDF could not be downloaded from arXiv."
        ) from error


def copy_paper_to_bucket(
    *,
    token: str,
    bucket_id: str,
    create: bool,
    private: bool,
    artifacts: list[HubArtifact],
    pdf_url: str | None,
    pdf_name: str | None,
) -> PaperBucketCopyResult:
    if not _REPO_ID_RE.fullmatch(bucket_id):
        raise PaperBucketError("Use a Bucket ID in namespace/name format.")
    if any(
        artifact.kind not in {"model", "dataset", "space"}
        or not _REPO_ID_RE.fullmatch(artifact.repo_id)
        for artifact in artifacts
    ):
        raise PaperBucketError("One or more Hugging Face artifact IDs are invalid.")

    copied: list[str] = []
    errors: list[tuple[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="pwc-hf-bucket-cache-") as cache_dir:
        api = HfApi(token=token)
        # ``copy_files`` downloads small text files through this method but does
        # not expose a cache_dir argument of its own. Deployed service users have
        # no writable home directory, so bind an operation-scoped cache explicitly.
        api.hf_hub_download = partial(api.hf_hub_download, cache_dir=cache_dir)
        try:
            if create:
                api.create_bucket(bucket_id, private=private, exist_ok=True)
        except HfHubHTTPError as error:
            raise _hub_error(error) from error

        for artifact in artifacts:
            try:
                api.copy_files(
                    artifact.source,
                    f"hf://buckets/{bucket_id}/{artifact.destination}",
                )
                copied.append(artifact.identifier)
            except HfHubHTTPError as error:
                failure = _hub_error(error)
                if failure.authorization_required:
                    raise failure from error
                errors.append((artifact.identifier, str(failure)))

        if pdf_url and pdf_name:
            pdf_path = Path(cache_dir) / "paper.pdf"
            try:
                _download_arxiv_pdf(pdf_url, pdf_path)
                api.batch_bucket_files(
                    bucket_id,
                    add=[(pdf_path, f"paper/{pdf_name}.pdf")],
                )
                copied.append("pdf")
            except HfHubHTTPError as error:
                failure = _hub_error(error)
                if failure.authorization_required:
                    raise failure from error
                errors.append(("pdf", str(failure)))
            except PaperBucketError as error:
                errors.append(("pdf", str(error)))

    return PaperBucketCopyResult(tuple(copied), tuple(errors))
