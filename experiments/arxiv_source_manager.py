#!/usr/bin/env python3
"""
ArXiv Source Manager for PapersWithCode

Advanced script for downloading, extracting, and managing arXiv paper sources
with integration capabilities for the PapersWithCode database.
"""

import requests
import tarfile
import json
from pathlib import Path
from typing import Optional, Union, Dict, List
from dataclasses import dataclass
from datetime import datetime
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ArxivPaper:
    """Data class for arXiv paper information."""

    arxiv_id: str
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    abstract: Optional[str] = None
    categories: Optional[List[str]] = None
    submitted_date: Optional[str] = None
    source_path: Optional[Path] = None
    main_tex_file: Optional[Path] = None


class ArxivSourceManager:
    """Manager class for arXiv source operations."""

    def __init__(self, base_dir: Union[str, Path] = "arxiv_sources"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(exist_ok=True)
        self.cache_file = self.base_dir / "download_cache.json"
        self.load_cache()

    def load_cache(self):
        """Load download cache from JSON file."""
        if self.cache_file.exists():
            with open(self.cache_file, "r") as f:
                self.cache = json.load(f)
        else:
            self.cache = {}

    def save_cache(self):
        """Save download cache to JSON file."""
        with open(self.cache_file, "w") as f:
            json.dump(self.cache, f, indent=2, default=str)

    def clean_arxiv_id(self, arxiv_id: str) -> str:
        """Clean and normalize arXiv ID."""
        if "arxiv.org" in arxiv_id:
            arxiv_id = arxiv_id.split("/")[-1]
        if arxiv_id.startswith("arXiv:"):
            arxiv_id = arxiv_id[6:]
        return arxiv_id

    def download_source(
        self,
        arxiv_id: str,
        force_redownload: bool = False,
        extract: bool = True,
        cleanup_archive: bool = True,
    ) -> Optional[ArxivPaper]:
        """
        Download and extract arXiv source with caching.

        Args:
            arxiv_id: ArXiv paper ID
            force_redownload: Force redownload even if cached
            extract: Whether to extract the archive
            cleanup_archive: Whether to delete archive after extraction

        Returns:
            ArxivPaper object with source information
        """
        clean_id = self.clean_arxiv_id(arxiv_id)

        # Check cache
        if not force_redownload and clean_id in self.cache:
            cached_path = Path(self.cache[clean_id]["source_path"])
            if cached_path.exists():
                logger.info(f"Using cached source for {clean_id}")
                return self._load_paper_from_cache(clean_id)

        # Create paper directory
        paper_dir = self.base_dir / clean_id
        paper_dir.mkdir(exist_ok=True)

        # Download
        url = f"https://arxiv.org/e-print/{clean_id}"
        archive_path = paper_dir / f"{clean_id}.tar.gz"

        logger.info(f"Downloading source for arXiv:{clean_id}")

        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()

            # Save archive
            with open(archive_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_size = archive_path.stat().st_size / 1024 / 1024
            logger.info(f"Downloaded: {archive_path} ({file_size:.1f} MB)")

            paper = ArxivPaper(arxiv_id=clean_id)

            if extract:
                # Extract archive
                source_dir = paper_dir / "source"
                source_dir.mkdir(exist_ok=True)

                with tarfile.open(archive_path, "r:gz") as tar:
                    # Security: filter for safe extraction
                    def safe_extract(members):
                        for member in members:
                            if member.isfile() and not member.name.startswith("/"):
                                yield member

                    tar.extractall(path=source_dir, members=safe_extract(tar))

                paper.source_path = source_dir
                paper.main_tex_file = self._find_main_tex(source_dir)

                # Count extracted files
                extracted_files = list(source_dir.rglob("*"))
                tex_files = [f for f in extracted_files if f.suffix == ".tex"]
                logger.info(
                    f"Extracted {len(extracted_files)} files, {len(tex_files)} LaTeX files"
                )

                if cleanup_archive:
                    archive_path.unlink()
            else:
                paper.source_path = archive_path

            # Update cache
            self.cache[clean_id] = {
                "arxiv_id": clean_id,
                "source_path": str(paper.source_path),
                "main_tex_file": str(paper.main_tex_file)
                if paper.main_tex_file
                else None,
                "download_date": datetime.now().isoformat(),
                "file_size_mb": file_size,
            }
            self.save_cache()

            return paper

        except Exception as e:
            logger.error(f"Failed to download {clean_id}: {e}")
            return None

    def _find_main_tex(self, source_dir: Path) -> Optional[Path]:
        """Find the main LaTeX file in source directory."""
        tex_files = list(source_dir.glob("*.tex"))

        if not tex_files:
            return None

        # Priority patterns for main files
        main_patterns = [
            "main.tex",
            "paper.tex",
            "manuscript.tex",
            "article.tex",
            "document.tex",
        ]

        # Check for common main file names
        for pattern in main_patterns:
            for tex_file in tex_files:
                if tex_file.name.lower() == pattern:
                    return tex_file

        # Look for files with \documentclass
        for tex_file in tex_files:
            try:
                with open(tex_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read(2000)
                    if "\\documentclass" in content:
                        return tex_file
            except Exception:
                continue

        # Return first .tex file as fallback
        return tex_files[0] if tex_files else None

    def _load_paper_from_cache(self, arxiv_id: str) -> ArxivPaper:
        """Load paper information from cache."""
        cache_data = self.cache[arxiv_id]
        paper = ArxivPaper(arxiv_id=arxiv_id)
        paper.source_path = Path(cache_data["source_path"])
        if cache_data.get("main_tex_file"):
            paper.main_tex_file = Path(cache_data["main_tex_file"])
        return paper

    def batch_download(
        self, arxiv_ids: List[str], max_workers: int = 3
    ) -> Dict[str, Optional[ArxivPaper]]:
        """
        Download multiple papers in batch with concurrent processing.

        Args:
            arxiv_ids: List of arXiv IDs to download
            max_workers: Maximum number of concurrent downloads

        Returns:
            Dictionary mapping arxiv_id to ArxivPaper (or None if failed)
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all download tasks
            future_to_id = {
                executor.submit(self.download_source, arxiv_id): arxiv_id
                for arxiv_id in arxiv_ids
            }

            # Collect results as they complete
            for future in as_completed(future_to_id):
                arxiv_id = future_to_id[future]
                try:
                    result = future.result()
                    results[arxiv_id] = result
                    if result:
                        logger.info(f"✓ Successfully downloaded {arxiv_id}")
                    else:
                        logger.error(f"✗ Failed to download {arxiv_id}")
                except Exception as e:
                    logger.error(f"✗ Exception downloading {arxiv_id}: {e}")
                    results[arxiv_id] = None

        return results

    def get_tex_content(self, paper: ArxivPaper) -> Optional[str]:
        """Get the content of the main LaTeX file."""
        if not paper.main_tex_file or not paper.main_tex_file.exists():
            return None

        try:
            with open(paper.main_tex_file, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read {paper.main_tex_file}: {e}")
            return None

    def extract_paper_info(self, paper: ArxivPaper) -> ArxivPaper:
        """Extract title, authors, and abstract from LaTeX source."""
        tex_content = self.get_tex_content(paper)
        if not tex_content:
            return paper

        # Extract title
        title_match = self._extract_latex_command(tex_content, "title")
        if title_match:
            paper.title = self._clean_latex_text(title_match)

        # Extract authors
        author_match = self._extract_latex_command(tex_content, "author")
        if author_match:
            # Simple author extraction (could be improved)
            authors_text = self._clean_latex_text(author_match)
            paper.authors = [a.strip() for a in authors_text.split(",")]

        # Extract abstract
        abstract_match = self._extract_latex_environment(tex_content, "abstract")
        if abstract_match:
            paper.abstract = self._clean_latex_text(abstract_match)

        return paper

    def _extract_latex_command(self, content: str, command: str) -> Optional[str]:
        """Extract content from LaTeX command like \\title{...}."""
        import re

        pattern = rf"\\{command}\s*\{{([^{{}}]*(?:\{{[^{{}}]*\}}[^{{}}]*)*)\}}"
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1) if match else None

    def _extract_latex_environment(self, content: str, env: str) -> Optional[str]:
        """Extract content from LaTeX environment like \\begin{abstract}...\\end{abstract}."""
        import re

        pattern = rf"\\begin\{{{env}\}}(.*?)\\end\{{{env}\}}"
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1) if match else None

    def _clean_latex_text(self, text: str) -> str:
        """Clean LaTeX text by removing common commands."""
        import re

        # Remove common LaTeX commands
        text = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", text)  # \command{text} -> text
        text = re.sub(r"\\[a-zA-Z]+", "", text)  # Remove \command
        text = re.sub(r"\s+", " ", text)  # Normalize whitespace
        return text.strip()

    def list_cached_papers(self) -> List[Dict]:
        """List all cached papers with their information."""
        return [
            {
                "arxiv_id": arxiv_id,
                "download_date": info.get("download_date"),
                "file_size_mb": info.get("file_size_mb"),
                "source_path": info.get("source_path"),
                "has_main_tex": bool(info.get("main_tex_file")),
            }
            for arxiv_id, info in self.cache.items()
        ]

    def cleanup_cache(self, remove_missing: bool = True):
        """Clean up cache by removing entries for missing files."""
        to_remove = []

        for arxiv_id, info in self.cache.items():
            source_path = Path(info["source_path"])
            if not source_path.exists():
                if remove_missing:
                    to_remove.append(arxiv_id)
                    logger.info(f"Removing missing cache entry: {arxiv_id}")

        for arxiv_id in to_remove:
            del self.cache[arxiv_id]

        if to_remove:
            self.save_cache()
            logger.info(f"Cleaned up {len(to_remove)} cache entries")


def main():
    """Command line interface."""
    import argparse

    parser = argparse.ArgumentParser(description="ArXiv Source Manager")
    parser.add_argument("command", choices=["download", "batch", "list", "cleanup"])
    parser.add_argument("--arxiv-id", help="ArXiv ID to download")
    parser.add_argument("--file", help="File with list of arXiv IDs (one per line)")
    parser.add_argument(
        "--output-dir", default="arxiv_sources", help="Output directory"
    )
    parser.add_argument("--force", action="store_true", help="Force redownload")
    parser.add_argument(
        "--extract-info", action="store_true", help="Extract paper info from LaTeX"
    )

    args = parser.parse_args()

    manager = ArxivSourceManager(args.output_dir)

    if args.command == "download":
        if not args.arxiv_id:
            print("Error: --arxiv-id required for download command")
            return

        paper = manager.download_source(args.arxiv_id, force_redownload=args.force)
        if paper:
            if args.extract_info:
                paper = manager.extract_paper_info(paper)
                print(f"Title: {paper.title}")
                print(f"Authors: {paper.authors}")
                if paper.abstract:
                    print(f"Abstract: {paper.abstract[:200]}...")
            print(f"Source: {paper.source_path}")
            if paper.main_tex_file:
                print(f"Main file: {paper.main_tex_file}")

    elif args.command == "batch":
        if not args.file:
            print("Error: --file required for batch command")
            return

        with open(args.file, "r") as f:
            arxiv_ids = [line.strip() for line in f if line.strip()]

        results = manager.batch_download(arxiv_ids)
        successful = sum(1 for r in results.values() if r is not None)
        print(f"Downloaded {successful}/{len(arxiv_ids)} papers successfully")

    elif args.command == "list":
        papers = manager.list_cached_papers()
        print(f"Found {len(papers)} cached papers:")
        for paper in papers:
            print(
                f"  {paper['arxiv_id']}: {paper['file_size_mb']:.1f}MB, {paper['download_date']}"
            )

    elif args.command == "cleanup":
        manager.cleanup_cache()


if __name__ == "__main__":
    main()
