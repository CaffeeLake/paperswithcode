"""
Thumbnail service for generating paper thumbnails.
Each thumbnail is generated from the first page of the paper's PDF.

This service handles:
- Downloading PDFs from ArXiv
- Converting the full first page to an image
- Reading/writing thumbnails from local or Hugging Face bucket storage
- Serving cached thumbnails
"""

import logging
import re
import time
from pathlib import Path
from typing import Optional

from huggingface_hub import HfFileSystem, batch_bucket_files, download_bucket_files
from PIL import Image
from pdf2image import convert_from_bytes

from backend.config import get_settings
from backend.utils.exceptions import ThumbnailGenerationError
from backend.services.arxiv_service import ArxivService

logger = logging.getLogger(__name__)


def build_thumbnail_filename(arxiv_id: str, version: str = "v1") -> str:
    """
    Build the canonical thumbnail filename for an ArXiv paper.
    """
    safe_id = arxiv_id.replace("/", "_").replace(".", "_")
    return f"{safe_id}_{version}.jpg"


class ThumbnailService:
    """
    Service for generating and managing PDF thumbnails.
    """

    def __init__(self):
        self.settings = get_settings()
        self.storage_backend = self.settings.thumbnail_storage_backend.lower()
        self.legacy_cache_dir = Path(self.settings.thumbnail_cache_dir)
        self.temp_cache_dir = Path(self.settings.thumbnail_temp_cache_dir)
        self.bucket_id = self.settings.thumbnail_hf_bucket_id.strip()
        self.bucket_prefix = self.settings.thumbnail_hf_bucket_prefix.strip("/")
        self.hf_token = self.settings.hf_token or None
        self.hf_fs = (
            HfFileSystem(token=self.hf_token)
            if self.storage_backend == "hf_bucket"
            else None
        )

        if self.storage_backend == "hf_bucket":
            if not self.bucket_id:
                raise ThumbnailGenerationError(
                    "PWC_THUMBNAIL_HF_BUCKET_ID is required for hf_bucket storage"
                )
            self.temp_cache_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.legacy_cache_dir.mkdir(parents=True, exist_ok=True)

        # Thumbnail settings
        self.thumbnail_width = 400  # Target width in pixels
        self.thumbnail_quality = 85  # JPEG quality
        self.pdf_timeout = 30  # Timeout for PDF downloads in seconds
        self.max_pdf_size = 50 * 1024 * 1024  # 50MB max PDF size

        # ArXiv service for API interactions
        self.arxiv_service = ArxivService()

    def parse_filename(self, filename: str) -> tuple[str, str]:
        """
        Parse a thumbnail filename into ArXiv ID and version.
        """
        if "/" in filename or "\\" in filename:
            raise ThumbnailGenerationError("Invalid thumbnail filename")

        match = re.fullmatch(
            r"(?P<base>[A-Za-z0-9_.-]+?)_(?P<version>v\d+)\.jpg",
            filename,
        )
        if not match:
            raise ThumbnailGenerationError("Invalid thumbnail filename")

        safe_id = match.group("base")
        if "_" not in safe_id:
            raise ThumbnailGenerationError("Invalid thumbnail filename")

        arxiv_id = safe_id.replace("_", ".")
        return arxiv_id, match.group("version")

    def validate_custom_filename(self, filename: str) -> None:
        """
        Validate a manually captured thumbnail filename.
        """
        if "/" in filename or "\\" in filename:
            raise ThumbnailGenerationError("Invalid custom thumbnail filename")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+\.jpg", filename):
            raise ThumbnailGenerationError("Invalid custom thumbnail filename")

    def get_filename(self, arxiv_id: str, version: str = "v1") -> str:
        """
        Get the stable thumbnail filename for a given ArXiv paper.
        """
        return build_thumbnail_filename(arxiv_id, version)

    def _get_cache_path(self, arxiv_id: str, version: str = "v1") -> Path:
        """
        Get the active local cache file path for a given ArXiv paper.
        """
        return self._get_active_cache_path(self.get_filename(arxiv_id, version))

    def _get_active_cache_path(self, filename: str) -> Path:
        cache_dir = (
            self.temp_cache_dir
            if self.storage_backend == "hf_bucket"
            else self.legacy_cache_dir
        )
        return cache_dir / filename

    def _get_legacy_cache_path(self, filename: str) -> Path:
        return self.legacy_cache_dir / filename

    def _get_bucket_key(self, filename: str) -> str:
        return f"{self.bucket_prefix}/{filename}" if self.bucket_prefix else filename

    def _get_bucket_uri(self, filename: str) -> str:
        return f"hf://buckets/{self.bucket_id}/{self._get_bucket_key(filename)}"

    def _download_from_bucket(self, filename: str) -> Optional[Path]:
        if self.storage_backend != "hf_bucket":
            return None

        cache_path = self._get_active_cache_path(filename)
        if cache_path.exists():
            return cache_path

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        download_bucket_files(
            self.bucket_id,
            [(self._get_bucket_key(filename), cache_path)],
            raise_on_missing_files=False,
            token=self.hf_token,
        )

        return cache_path if cache_path.exists() else None

    def _upload_to_bucket(self, thumbnail_path: Path, filename: str) -> None:
        if self.storage_backend != "hf_bucket":
            return

        batch_bucket_files(
            self.bucket_id,
            add=[(thumbnail_path, self._get_bucket_key(filename))],
            token=self.hf_token,
        )

    def _bucket_thumbnail_exists(self, filename: str) -> bool:
        if self.storage_backend != "hf_bucket" or self.hf_fs is None:
            return False

        try:
            return bool(self.hf_fs.exists(self._get_bucket_uri(filename)))
        except Exception as exc:
            logger.warning(
                "Failed to check thumbnail bucket object %s: %s", filename, exc
            )
            return False

    def _convert_pdf_to_thumbnail(self, pdf_content: bytes) -> Image.Image:
        """
        Convert PDF first page to thumbnail image.

        Args:
            pdf_content: PDF file content as bytes

        Returns:
            PIL Image of the thumbnail

        Raises:
            ThumbnailGenerationError: If conversion fails
        """
        try:
            # Convert first page only with reasonable DPI
            images = convert_from_bytes(
                pdf_content,
                first_page=1,
                last_page=1,
                dpi=150,  # Good balance of quality and performance
                fmt="jpeg",
            )

            if not images:
                raise ThumbnailGenerationError("No pages found in PDF")

            image = images[0]

            # Resize the full first page to target width while maintaining aspect ratio
            aspect_ratio = image.height / image.width
            target_height = int(self.thumbnail_width * aspect_ratio)

            thumbnail = image.resize(
                (self.thumbnail_width, target_height), Image.Resampling.LANCZOS
            )

            return thumbnail

        except Exception as e:
            raise ThumbnailGenerationError(f"Failed to convert PDF to image: {str(e)}")

    def _save_thumbnail(self, image: Image.Image, cache_path: Path) -> None:
        """
        Save thumbnail image to cache.

        Args:
            image: PIL Image to save
            cache_path: Path where to save the image
        """
        try:
            # Convert to RGB if necessary (for JPEG)
            if image.mode != "RGB":
                image = image.convert("RGB")

            image.save(
                cache_path, "JPEG", quality=self.thumbnail_quality, optimize=True
            )
        except Exception as e:
            raise ThumbnailGenerationError(f"Failed to save thumbnail: {str(e)}")

    def get_existing_thumbnail_path(self, filename: str) -> Optional[Path]:
        """
        Return an existing thumbnail path from active cache, bucket, or legacy cache.
        """
        self.parse_filename(filename)
        return self._get_existing_thumbnail_path_unchecked(filename)

    def get_local_thumbnail_path(self, filename: str) -> Optional[Path]:
        """
        Return an existing thumbnail path from on-disk caches only.

        Used by the request-serving path to guarantee that no per-request HF
        bucket round-trip happens; the bucket is kept in sync with the active
        local cache by the `mirror_thumbnails_to_disk` cron.
        """
        self.parse_filename(filename)
        active_cache_path = self._get_active_cache_path(filename)
        if active_cache_path.exists():
            return active_cache_path

        legacy_cache_path = self._get_legacy_cache_path(filename)
        if legacy_cache_path.exists():
            return legacy_cache_path

        return None

    def get_existing_custom_thumbnail_path(self, filename: str) -> Optional[Path]:
        """
        Return an existing manually captured thumbnail path.
        """
        self.validate_custom_filename(filename)
        return self._get_existing_thumbnail_path_unchecked(filename)

    def _get_existing_thumbnail_path_unchecked(self, filename: str) -> Optional[Path]:
        active_cache_path = self._get_active_cache_path(filename)
        if active_cache_path.exists():
            return active_cache_path

        bucket_path = self._download_from_bucket(filename)
        if bucket_path:
            return bucket_path

        legacy_cache_path = self._get_legacy_cache_path(filename)
        if legacy_cache_path.exists():
            try:
                self._upload_to_bucket(legacy_cache_path, filename)
            except Exception as exc:
                logger.warning(
                    "Failed to upload legacy thumbnail %s to bucket: %s",
                    filename,
                    exc,
                )
            return legacy_cache_path

        return None

    async def get_or_generate_thumbnail(self, filename: str) -> Path:
        """
        Return an existing thumbnail or generate it from the filename's ArXiv ID.
        """
        arxiv_id, version = self.parse_filename(filename)
        existing_path = self.get_existing_thumbnail_path(filename)
        if existing_path:
            return existing_path

        return await self.generate_thumbnail(arxiv_id, version)

    async def generate_thumbnail(self, arxiv_id: str, version: str = "v1") -> Path:
        """
        Generate thumbnail for a paper using ArXiv service.

        Args:
            arxiv_id: ArXiv ID of the paper
            version: Paper version

        Returns:
            Path to the generated thumbnail file

        Raises:
            ThumbnailGenerationError: If generation fails
        """
        filename = self.get_filename(arxiv_id, version)
        existing_path = self.get_existing_thumbnail_path(filename)
        if existing_path:
            return existing_path

        cache_path = self._get_cache_path(arxiv_id, version)
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Download PDF using ArXiv service (handles rate limiting)
            pdf_content = await self.arxiv_service.download_pdf(arxiv_id, version)

            if pdf_content is None:
                raise ThumbnailGenerationError(
                    f"Could not download PDF for ArXiv ID {arxiv_id}"
                )

            # Convert to thumbnail
            thumbnail = self._convert_pdf_to_thumbnail(pdf_content)

            # Save to cache
            self._save_thumbnail(thumbnail, cache_path)
            self._upload_to_bucket(cache_path, filename)

            return cache_path

        except ThumbnailGenerationError:
            raise
        except Exception as e:
            raise ThumbnailGenerationError(
                f"Unexpected error generating thumbnail: {str(e)}"
            )

    def get_thumbnail_url(self, arxiv_id: str, version: str = "v1") -> Optional[str]:
        """
        Get the URL for a cached thumbnail.

        Args:
            arxiv_id: ArXiv ID of the paper
            version: Paper version

        Returns:
            URL to the thumbnail or None if not cached
        """
        filename = self.get_filename(arxiv_id, version)

        active_cache_path = self._get_active_cache_path(filename)
        legacy_cache_path = self._get_legacy_cache_path(filename)
        if (
            active_cache_path.exists()
            or legacy_cache_path.exists()
            or self._bucket_thumbnail_exists(filename)
        ):
            return f"/api/thumbnails/{filename}"

        return None

    def cleanup_old_thumbnails(self, max_age_days: int = 30) -> int:
        """
        Clean up old cached thumbnails.

        Args:
            max_age_days: Maximum age in days for cached thumbnails

        Returns:
            Number of files deleted
        """
        deleted_count = 0
        max_age_seconds = max_age_days * 24 * 60 * 60
        current_time = time.time()

        cache_dir = (
            self.temp_cache_dir
            if self.storage_backend == "hf_bucket"
            else self.legacy_cache_dir
        )

        for thumbnail_file in cache_dir.glob("*.jpg"):
            try:
                file_age = current_time - thumbnail_file.stat().st_mtime
                if file_age > max_age_seconds:
                    thumbnail_file.unlink()
                    deleted_count += 1
            except Exception:
                # Skip files that can't be processed
                continue

        return deleted_count

    def get_cache_stats(self) -> dict:
        """
        Get statistics about the thumbnail cache.

        Returns:
            Dictionary with cache statistics
        """
        try:
            cache_dir = (
                self.temp_cache_dir
                if self.storage_backend == "hf_bucket"
                else self.legacy_cache_dir
            )
            thumbnail_files = list(cache_dir.glob("*.jpg"))
            total_files = len(thumbnail_files)

            total_size = sum(f.stat().st_size for f in thumbnail_files)
            total_size_mb = total_size / (1024 * 1024)

            stats = {
                "total_files": total_files,
                "total_size_mb": round(total_size_mb, 2),
                "cache_dir": str(cache_dir),
                "storage_backend": self.storage_backend,
            }
            if self.storage_backend == "hf_bucket":
                stats.update(
                    {
                        "bucket_id": self.bucket_id,
                        "bucket_prefix": self.bucket_prefix,
                        "legacy_cache_dir": str(self.legacy_cache_dir),
                    }
                )
            return stats
        except Exception:
            return {
                "total_files": 0,
                "total_size_mb": 0,
                "cache_dir": str(
                    self.temp_cache_dir
                    if self.storage_backend == "hf_bucket"
                    else self.legacy_cache_dir
                ),
                "storage_backend": self.storage_backend,
            }
