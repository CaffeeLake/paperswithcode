#!/usr/bin/env python3
"""
LaTeX Consolidator for LLM Processing

Based on axcell's approach, this script consolidates multi-file LaTeX papers
into a single comprehensive text file that can be fed to LLMs for extraction
of evaluation results, GitHub URLs, and project pages.
"""

import re
import codecs
from pathlib import Path
from typing import Optional, List, Dict, Set
import argparse
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LatexConsolidator:
    """Consolidates multi-file LaTeX papers into single text for LLM processing."""

    def __init__(self):
        # Regex patterns for LaTeX parsing
        self.doccls = re.compile(r"\s*\\documentclass")
        self.docbeg = re.compile(r"\s*\\begin\s*\{\s*document\s*\}")
        self.title = re.compile(r"\s*\\(icml)?title\s*\{(?P<title>[^%}]*)")
        self.input_include = re.compile(r"\\(input|include)\s*\{([^}]+)\}")
        self.url_patterns = [
            re.compile(r"\\url\s*\{([^}]+)\}"),
            re.compile(r"\\href\s*\{([^}]+)\}"),
            re.compile(r"https?://[^\s\}]+"),
            re.compile(r"github\.com/[^\s\}]+"),
        ]

        # Auxiliary file patterns (from axcell)
        self.aux = re.compile(
            r"(rebuttal\s+|instructions\s+(for\s+\\confname|.*proceedings)|(supplementary|supplemental)\s+materials?|appendix|author\s+guidelines|ieeetran\.cls|formatting\s+instructions)"
        )

        # LaTeX commands to clean
        self.latex_commands = [
            re.compile(r"\\[a-zA-Z]+\*?\[[^\]]*\]"),  # Commands with optional args
            re.compile(r"\\[a-zA-Z]+\*?\{[^}]*\}"),  # Commands with required args
            re.compile(r"\\[a-zA-Z]+\*?"),  # Simple commands
            re.compile(r"\{[^}]*\}"),  # Remaining braces
            re.compile(r"\\\\"),  # Line breaks
            re.compile(r"[{}]"),  # Remaining braces
            re.compile(r"%.*$", re.MULTILINE),  # Comments
        ]

    def is_aux_title(self, title: str) -> bool:
        """Check if title indicates auxiliary file (from axcell)."""
        title = title.strip().lower()
        return bool(self.aux.search(title))

    def calc_priority(self, path: Path) -> int:
        """Calculate priority for main file detection (from axcell)."""
        priority = 0

        # Special case for ms.tex
        if path.name.lower() == "ms.tex":
            return 30

        try:
            with codecs.open(path, "r", encoding="utf8", errors="ignore") as f:
                # Look for \documentclass
                for line in f:
                    if self.doccls.match(line):
                        priority += 10
                        break

                # Look for \title
                for line in f:
                    m = self.title.match(line)
                    if m:
                        priority += 5
                        title = m["title"]
                        if self.is_aux_title(title):
                            priority = 5  # Downgrade auxiliary files
                        break
        except Exception as e:
            logger.warning(f"Error reading {path}: {e}")

        return priority

    def guess_main_file(self, source_dir: Path) -> Optional[Path]:
        """Find the main LaTeX file (from axcell's guess_main.py)."""
        tex_files = list(source_dir.glob("*.tex"))

        if not tex_files:
            return None

        if len(tex_files) == 1:
            return tex_files[0]

        # Sort by filename first
        tex_files = sorted(tex_files, key=lambda p: p.stem.lower())

        # Calculate priorities and sort
        with_priority = [(f, self.calc_priority(f)) for f in tex_files]
        with_priority = sorted(with_priority, key=lambda fp: fp[1], reverse=True)

        main_file = with_priority[0][0]
        logger.info(
            f"Selected main file: {main_file} (priority: {with_priority[0][1]})"
        )

        return main_file

    def extract_urls(self, text: str) -> List[str]:
        """Extract URLs from LaTeX text."""
        urls = []
        for pattern in self.url_patterns:
            matches = pattern.findall(text)
            urls.extend(matches)

        # Clean and deduplicate
        cleaned_urls = []
        for url in urls:
            if isinstance(url, tuple):
                url = url[0]  # From href matches
            url = url.strip(".,;")
            if url and url not in cleaned_urls:
                cleaned_urls.append(url)

        return cleaned_urls

    def extract_urls_from_style_files(self, source_dir: Path) -> List[str]:
        """Extract URLs from .sty and .bib files."""
        urls = []

        # Check .sty files
        for sty_file in source_dir.glob("*.sty"):
            try:
                with codecs.open(sty_file, "r", encoding="utf8", errors="ignore") as f:
                    content = f.read()
                    sty_urls = self.extract_urls(content)
                    urls.extend(sty_urls)
                    logger.info(
                        f"Found {len(sty_urls)} URLs in style file: {sty_file.name}"
                    )
            except Exception as e:
                logger.warning(f"Error reading style file {sty_file}: {e}")

        # Check .bib files
        for bib_file in source_dir.glob("*.bib"):
            try:
                with codecs.open(bib_file, "r", encoding="utf8", errors="ignore") as f:
                    content = f.read()
                    bib_urls = self.extract_urls(content)
                    urls.extend(bib_urls)
                    logger.info(
                        f"Found {len(bib_urls)} URLs in bibliography: {bib_file.name}"
                    )
            except Exception as e:
                logger.warning(f"Error reading bibliography file {bib_file}: {e}")

        return urls

    def clean_latex_text(self, text: str) -> str:
        """Clean LaTeX commands from text."""
        # Remove comments first
        text = re.sub(r"%.*$", "", text, flags=re.MULTILINE)

        # Remove common LaTeX environments
        text = re.sub(r"\\begin\{[^}]+\}.*?\\end\{[^}]+\}", "", text, flags=re.DOTALL)

        # Remove LaTeX commands
        for pattern in self.latex_commands:
            text = pattern.sub("", text)

        # Clean up whitespace
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n\s*\n", "\n\n", text)

        return text.strip()

    def resolve_inputs(
        self, main_file: Path, source_dir: Path = None, processed: Set[Path] = None
    ) -> str:
        """Recursively resolve \\input and \\include commands."""
        if processed is None:
            processed = set()

        if source_dir is None:
            source_dir = main_file.parent

        if main_file in processed:
            logger.warning(f"Circular dependency detected: {main_file}")
            return ""

        processed.add(main_file)

        try:
            with codecs.open(main_file, "r", encoding="utf8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            logger.error(f"Error reading {main_file}: {e}")
            return ""

        # Find all input/include commands
        def replace_input(match):
            filename = match.group(2)

            # Add .tex extension if missing
            if not filename.endswith(".tex"):
                filename += ".tex"

            # Try multiple possible paths for the input file
            possible_paths = [
                main_file.parent / filename,  # Relative to current file
                source_dir / filename,  # Relative to project root
                source_dir / filename.replace("tabs/", ""),  # Remove tabs/ prefix
            ]

            # Add tabs/ directory if it exists
            tabs_dir = source_dir / "tabs"
            if tabs_dir.exists() and "tabs/" in filename:
                possible_paths.append(tabs_dir / filename.replace("tabs/", ""))

            input_path = None
            for path in possible_paths:
                if path.exists():
                    input_path = path
                    break

            if not input_path:
                logger.warning(
                    f"Input file not found. Tried: {[str(p) for p in possible_paths]}"
                )
                return f"% FILE NOT FOUND: {filename}\n"

            logger.info(f"Including: {input_path}")

            # Recursively process the included file
            included_content = self.resolve_inputs(
                input_path, source_dir, processed.copy()
            )
            return f"\n% === INCLUDED FILE: {filename} ===\n{included_content}\n% === END OF {filename} ===\n"

        # Replace all input/include commands
        resolved_content = self.input_include.sub(replace_input, content)

        return resolved_content

    def include_style_content(self, source_dir: Path, latex_content: str) -> str:
        """Include relevant content from style files in the correct reading order."""
        # Find usepackage commands
        usepackage_pattern = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}")
        packages = usepackage_pattern.findall(latex_content)

        # Collect style file content
        style_definitions = []
        maketitle_expansions = {}

        for package in packages:
            sty_file = source_dir / f"{package}.sty"
            if sty_file.exists():
                try:
                    with codecs.open(
                        sty_file, "r", encoding="utf8", errors="ignore"
                    ) as f:
                        sty_content = f.read()

                    # Extract URL command definitions
                    url_commands = re.findall(
                        r"\\newcommand\{\\[^}]+\}\{[^}]*https?://[^}]+\}", sty_content
                    )
                    maketitle_content = self._extract_maketitle_content(sty_content)

                    if url_commands:
                        logger.info(
                            f"Found URL definitions in style file: {package}.sty"
                        )
                        for cmd in url_commands:
                            style_definitions.append(cmd)

                    if maketitle_content:
                        logger.info(
                            f"Found maketitle content in style file: {package}.sty"
                        )
                        maketitle_expansions[package] = maketitle_content

                except Exception as e:
                    logger.warning(f"Error processing style file {sty_file}: {e}")

        # Add style definitions at the beginning (after documentclass)
        if style_definitions:
            definitions_section = "\n% === URL DEFINITIONS FROM STYLE FILES ===\n"
            for definition in style_definitions:
                definitions_section += f"{definition}\n"
            definitions_section += "% === END OF URL DEFINITIONS ===\n"

            # Insert after \documentclass and \usepackage commands
            doc_start = re.search(
                r"(\\documentclass.*?\n(?:\\usepackage.*?\n)*)",
                latex_content,
                re.DOTALL,
            )
            if doc_start:
                insert_pos = doc_start.end()
                latex_content = (
                    latex_content[:insert_pos]
                    + definitions_section
                    + latex_content[insert_pos:]
                )
            else:
                latex_content = definitions_section + latex_content

        # Replace \maketitle with expanded content
        if maketitle_expansions:

            def replace_maketitle(match):
                expanded_content = "\n% === EXPANDED MAKETITLE CONTENT ===\n"
                expanded_content += "% Title and author information would appear here\n"

                # Add URL tables from maketitle
                for package, content in maketitle_expansions.items():
                    expanded_content += f"\n% URLs from {package}.sty maketitle:\n"
                    expanded_content += f"{content}\n"

                expanded_content += "% === END OF MAKETITLE EXPANSION ===\n"
                return expanded_content

            latex_content = re.sub(r"\\maketitle\s*", replace_maketitle, latex_content)
            logger.info("Expanded \\maketitle with URL content in reading order")

        return latex_content

    def _extract_maketitle_content(self, sty_content: str) -> str:
        """Extract URL-containing content from maketitle definition."""
        # Look for the table with URLs in maketitle
        maketitle_match = re.search(
            r"\\def\\@maketitle\{.*?\\begin\{tabular\}\{rl\}(.*?)\\end\{tabular\}.*?\}",
            sty_content,
            re.DOTALL,
        )
        if maketitle_match:
            table_content = maketitle_match.group(1)
            # Only include lines that have URLs
            url_lines = []
            for line in table_content.split("\n"):
                if "url{" in line.lower() or "https://" in line or "http://" in line:
                    url_lines.append(line.strip())
            if url_lines:
                return (
                    "\\begin{tabular}{rl}\n" + "\n".join(url_lines) + "\n\\end{tabular}"
                )
        return ""

    def consolidate_paper(self, source_dir: Path) -> Dict:
        """Consolidate a paper into a single text with metadata."""
        source_dir = Path(source_dir)

        if not source_dir.exists():
            raise FileNotFoundError(f"Source directory not found: {source_dir}")

        # Find main file
        main_file = self.guess_main_file(source_dir)
        if not main_file:
            raise ValueError(f"No suitable .tex file found in {source_dir}")

        logger.info(f"Processing paper from: {source_dir}")
        logger.info(f"Main file: {main_file}")

        # Resolve all inputs recursively
        full_latex = self.resolve_inputs(main_file, source_dir)

        # Include relevant content from style files
        full_latex = self.include_style_content(source_dir, full_latex)

        # Extract URLs from LaTeX content and style files
        urls = self.extract_urls(full_latex)
        style_urls = self.extract_urls_from_style_files(source_dir)
        urls.extend(style_urls)

        # Clean LaTeX for LLM processing
        clean_text = self.clean_latex_text(full_latex)

        # Extract basic metadata
        title_match = self.title.search(full_latex)
        title = title_match.group("title").strip() if title_match else "Unknown"

        # Count files processed
        tex_files = list(source_dir.rglob("*.tex"))

        result = {
            "source_dir": str(source_dir),
            "main_file": str(main_file),
            "title": title,
            "urls": urls,
            "github_urls": [url for url in urls if "github.com" in url.lower()],
            "tex_files_count": len(tex_files),
            "raw_latex": full_latex,
            "clean_text": clean_text,
            "char_count": len(clean_text),
            "word_count": len(clean_text.split()),
        }

        return result

    def save_consolidated(self, result: Dict, output_path: Path):
        """Save consolidated paper to files."""
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        # Save clean text for LLM
        clean_file = output_path / "paper_clean.txt"
        with open(clean_file, "w", encoding="utf-8") as f:
            f.write(result["clean_text"])

        # Save raw LaTeX
        raw_file = output_path / "paper_raw.tex"
        with open(raw_file, "w", encoding="utf-8") as f:
            f.write(result["raw_latex"])

        # Save metadata
        import json

        meta_file = output_path / "metadata.json"
        metadata = {
            k: v for k, v in result.items() if k not in ["raw_latex", "clean_text"]
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Saved consolidated paper to: {output_path}")
        logger.info(f"  Clean text: {clean_file} ({result['char_count']} chars)")
        logger.info(f"  Raw LaTeX: {raw_file}")
        logger.info(f"  Metadata: {meta_file}")

        if result["github_urls"]:
            logger.info(f"  Found GitHub URLs: {result['github_urls']}")


def main():
    """Command line interface."""
    parser = argparse.ArgumentParser(
        description="Consolidate LaTeX papers for LLM processing"
    )
    parser.add_argument("source_dir", help="Directory containing LaTeX source files")
    parser.add_argument(
        "-o", "--output", help="Output directory (default: source_dir/consolidated)"
    )
    parser.add_argument(
        "--clean-only", action="store_true", help="Output only clean text to stdout"
    )
    parser.add_argument(
        "--urls-only", action="store_true", help="Output only URLs to stdout"
    )

    args = parser.parse_args()

    consolidator = LatexConsolidator()

    try:
        result = consolidator.consolidate_paper(args.source_dir)

        if args.urls_only:
            for url in result["urls"]:
                print(url)
            return

        if args.clean_only:
            print(result["clean_text"])
            return

        # Save to output directory
        if args.output:
            output_path = Path(args.output)
        else:
            output_path = Path(args.source_dir) / "consolidated"

        consolidator.save_consolidated(result, output_path)

        # Print summary
        print("\n=== CONSOLIDATION SUMMARY ===")
        print(f"Title: {result['title']}")
        print(f"Source: {result['source_dir']}")
        print(f"Main file: {result['main_file']}")
        print(f"LaTeX files processed: {result['tex_files_count']}")
        print(
            f"Clean text: {result['word_count']} words, {result['char_count']} characters"
        )
        print(f"URLs found: {len(result['urls'])}")
        if result["github_urls"]:
            print(f"GitHub URLs: {result['github_urls']}")

    except Exception as e:
        logger.error(f"Error processing paper: {e}")
        return 1


if __name__ == "__main__":
    main()
