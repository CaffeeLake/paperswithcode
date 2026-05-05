"""
Thumbnail API router.

Provides endpoints for:
- Generating thumbnails for papers
- Serving cached thumbnails
- Managing thumbnail cache
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.services.thumbnail_service import ThumbnailService
from backend.services.paper_service import PaperService
from backend.utils.exceptions import PaperNotFoundError

router = APIRouter(prefix="/thumbnails", tags=["thumbnails"])


def get_thumbnail_service() -> ThumbnailService:
    """Dependency to get thumbnail service instance."""
    return ThumbnailService()


@router.get("/{filename}")
async def serve_thumbnail(
    filename: str, thumbnail_service: ThumbnailService = Depends(get_thumbnail_service)
):
    """
    Serve a thumbnail file with on-demand generation.

    This endpoint follows Hugging Face's approach:
    1. Check if thumbnail exists in cache
    2. If not, generate it on-demand from the ArXiv ID in filename
    3. Serve with heavy caching headers (7 days)

    Args:
        filename: Name of the thumbnail file (format: {arxiv_id}_{version}.jpg)

    Returns:
        FileResponse with the thumbnail image

    Raises:
        HTTPException: If generation fails or invalid filename
    """
    try:
        thumbnail_path = await thumbnail_service.get_or_generate_thumbnail(filename)
        return FileResponse(
            path=thumbnail_path,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, s-maxage=604800, max-age=604800"
            },  # 7 days cache like HF
        )
    except Exception:
        # If generation fails, return a 404 with cache headers to avoid repeated attempts
        raise HTTPException(
            status_code=404,
            detail="Thumbnail not available",
            headers={"Cache-Control": "public, max-age=3600"},  # Cache 404 for 1 hour
        )


@router.post("/generate/{paper_id}")
async def generate_thumbnail(
    paper_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_database_session),
    thumbnail_service: ThumbnailService = Depends(get_thumbnail_service),
):
    """
    Generate a thumbnail for a paper.

    Args:
        paper_id: ID of the paper to generate thumbnail for
        background_tasks: FastAPI background tasks
        db: Database session
        thumbnail_service: Thumbnail service instance

    Returns:
        Dictionary with thumbnail URL or generation status

    Raises:
        HTTPException: If paper not found or generation fails
    """
    try:
        # Get paper details
        paper_service = PaperService(db)
        paper = paper_service.get_paper_by_id(paper_id)

        if not paper.arxiv_id:
            raise HTTPException(
                status_code=400,
                detail="Paper does not have an ArXiv ID, cannot generate thumbnail",
            )

        # Check if thumbnail already exists
        existing_url = thumbnail_service.get_thumbnail_url(
            paper.arxiv_id, paper.version
        )
        if existing_url:
            return {
                "thumbnail_url": existing_url,
                "status": "cached",
                "message": "Thumbnail already exists",
            }

        # Generate thumbnail in background
        async def generate_in_background():
            try:
                await thumbnail_service.generate_thumbnail(
                    paper.arxiv_id, paper.version
                )
            except Exception as e:
                # Log error but don't fail the request
                print(
                    f"Background thumbnail generation failed for {paper.arxiv_id}: {e}"
                )

        background_tasks.add_task(generate_in_background)

        return {
            "thumbnail_url": None,
            "status": "generating",
            "message": "Thumbnail generation started in background",
        }

    except PaperNotFoundError:
        raise HTTPException(status_code=404, detail="Paper not found")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to generate thumbnail: {str(e)}"
        )


@router.get("/status/{paper_id}")
async def get_thumbnail_status(
    paper_id: str,
    db: Session = Depends(get_database_session),
    thumbnail_service: ThumbnailService = Depends(get_thumbnail_service),
):
    """
    Check if a thumbnail exists for a paper.

    Args:
        paper_id: ID of the paper to check
        db: Database session
        thumbnail_service: Thumbnail service instance

    Returns:
        Dictionary with thumbnail status and URL if available

    Raises:
        HTTPException: If paper not found
    """
    try:
        # Get paper details
        paper_service = PaperService(db)
        paper = paper_service.get_paper_by_id(paper_id)

        if not paper.arxiv_id:
            return {
                "has_thumbnail": False,
                "thumbnail_url": None,
                "reason": "No ArXiv ID",
            }

        # Check if thumbnail exists
        thumbnail_url = thumbnail_service.get_thumbnail_url(
            paper.arxiv_id, paper.version
        )

        return {
            "has_thumbnail": thumbnail_url is not None,
            "thumbnail_url": thumbnail_url,
            "arxiv_id": paper.arxiv_id,
            "version": paper.version,
        }

    except PaperNotFoundError:
        raise HTTPException(status_code=404, detail="Paper not found")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to check thumbnail status: {str(e)}"
        )


@router.get("/cache/stats")
async def get_cache_stats(
    thumbnail_service: ThumbnailService = Depends(get_thumbnail_service),
):
    """
    Get thumbnail cache statistics.

    Returns:
        Dictionary with cache statistics
    """
    return thumbnail_service.get_cache_stats()


@router.post("/cache/cleanup")
async def cleanup_cache(
    max_age_days: int = 30,
    thumbnail_service: ThumbnailService = Depends(get_thumbnail_service),
):
    """
    Clean up old cached thumbnails.

    Args:
        max_age_days: Maximum age in days for cached thumbnails

    Returns:
        Dictionary with cleanup results
    """
    try:
        deleted_count = thumbnail_service.cleanup_old_thumbnails(max_age_days)
        return {
            "deleted_count": deleted_count,
            "max_age_days": max_age_days,
            "message": f"Deleted {deleted_count} old thumbnails",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to cleanup cache: {str(e)}"
        )
