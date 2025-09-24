"""
Thumbnail service for generating paper thumbnails.
Each thumbnail is generated from the first page of the paper's PDF.

This service handles:
- Downloading PDFs from ArXiv
- Converting first page to image
- Cropping to show upper half
- Caching thumbnails
- Serving cached thumbnails
"""

from pathlib import Path
from typing import Optional
from io import BytesIO

import requests
from PIL import Image
from pdf2image import convert_from_bytes

from backend.config import get_settings
from backend.utils.exceptions import ThumbnailGenerationError
from backend.services.arxiv_service import ArxivService


class ThumbnailService:
    """
    Service for generating and managing PDF thumbnails.
    """

    def __init__(self):
        self.settings = get_settings()
        self.cache_dir = Path(self.settings.thumbnail_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Thumbnail settings
        self.thumbnail_width = 400  # Target width in pixels
        self.thumbnail_quality = 85  # JPEG quality
        self.pdf_timeout = 30  # Timeout for PDF downloads in seconds
        self.max_pdf_size = 50 * 1024 * 1024  # 50MB max PDF size

        # ArXiv service for API interactions
        self.arxiv_service = ArxivService()

    def _get_cache_path(self, arxiv_id: str, version: str = "v1") -> Path:
        """
        Get the cache file path for a given ArXiv paper.

        Args:
            arxiv_id: ArXiv ID (e.g., "1805.10616")
            version: Paper version (e.g., "v1", "v2")

        Returns:
            Path to cached thumbnail file
        """
        # Create a safe filename from arxiv_id and version
        safe_id = arxiv_id.replace("/", "_").replace(".", "_")
        filename = f"{safe_id}_{version}.jpg"
        return self.cache_dir / filename

    def _download_pdf(self, pdf_url: str) -> bytes:
        """
        Download PDF from URL with proper error handling.

        Args:
            pdf_url: URL to the PDF file

        Returns:
            PDF content as bytes

        Raises:
            ThumbnailGenerationError: If download fails
        """
        try:
            headers = {
                "User-Agent": "PapersWithCode-Bot/1.0 (https://paperswithcode.ai)"
            }

            response = requests.get(
                pdf_url, headers=headers, timeout=self.pdf_timeout, stream=True
            )
            response.raise_for_status()

            # Check content length
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > self.max_pdf_size:
                raise ThumbnailGenerationError(f"PDF too large: {content_length} bytes")

            # Download with size limit
            content = BytesIO()
            downloaded = 0

            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    downloaded += len(chunk)
                    if downloaded > self.max_pdf_size:
                        raise ThumbnailGenerationError(
                            f"PDF too large: {downloaded} bytes"
                        )
                    content.write(chunk)

            return content.getvalue()

        except requests.RequestException as e:
            raise ThumbnailGenerationError(f"Failed to download PDF: {str(e)}")
        except Exception as e:
            raise ThumbnailGenerationError(
                f"Unexpected error downloading PDF: {str(e)}"
            )

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

            # Crop to upper half
            width, height = image.size
            upper_half = image.crop((0, 0, width, height // 2))

            # Resize to target width while maintaining aspect ratio
            aspect_ratio = upper_half.height / upper_half.width
            target_height = int(self.thumbnail_width * aspect_ratio)

            thumbnail = upper_half.resize(
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
        cache_path = self._get_cache_path(arxiv_id, version)

        # Return cached version if it exists
        if cache_path.exists():
            return cache_path

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
        cache_path = self._get_cache_path(arxiv_id, version)

        if cache_path.exists():
            # Return relative URL that will be served by the API
            filename = cache_path.name
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
        import time

        deleted_count = 0
        max_age_seconds = max_age_days * 24 * 60 * 60
        current_time = time.time()

        for thumbnail_file in self.cache_dir.glob("*.jpg"):
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
            thumbnail_files = list(self.cache_dir.glob("*.jpg"))
            total_files = len(thumbnail_files)

            total_size = sum(f.stat().st_size for f in thumbnail_files)
            total_size_mb = total_size / (1024 * 1024)

            return {
                "total_files": total_files,
                "total_size_mb": round(total_size_mb, 2),
                "cache_dir": str(self.cache_dir),
            }
        except Exception:
            return {
                "total_files": 0,
                "total_size_mb": 0,
                "cache_dir": str(self.cache_dir),
            }
