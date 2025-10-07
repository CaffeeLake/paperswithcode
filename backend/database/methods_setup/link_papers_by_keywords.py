#!/usr/bin/env python3
"""
Link papers to methods based on keyword matching in titles and abstracts.

Rules:
1. Case-sensitive matching for all-caps methods (BPE, CNN, BERT, GPT, etc.)
2. Only match methods that have keywords defined
3. Prefer longest matching keyword (e.g., GPT-2 over GPT, YOLOv8 over YOLO)
"""

import re
from typing import Dict, List, Set, Tuple
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

# Case-sensitive method names (all-caps or specific versions)
CASE_SENSITIVE_METHODS = {
    "BPE",
    "CNN",
    "BERT",
    "GPT",
    "DDPM",
    "GPT-4o",
    "ViT",
    "GPT-2",
    "GPT-3",
    "GPT-4",
    "YOLOv3",
    "YOLOv8",
    "BigGAN",
    "MoE",
    "ColBERT",
    "NeRF",
    "DiT",
    "RoPE",
    "DUSt3R",
    "T5",
    "LSTM",
    "RNN",
    "GAN",
    "VAE",
    "BLEU",
    "ROUGE",
    "DDIM",
    "SVM",
    "ReLU",
    "GELU",
    "GPT-3.5",
    "GPT-4-turbo",
}


def is_case_sensitive(method_name: str, keywords: List[str]) -> bool:
    """
    Determine if a method should use case-sensitive matching.

    Args:
        method_name: Name of the method
        keywords: List of keywords for the method

    Returns:
        True if case-sensitive matching should be used
    """
    # Check if method name is in the explicit case-sensitive list
    if method_name in CASE_SENSITIVE_METHODS:
        return True

    # Check if any keyword is all-caps (2+ chars)
    for keyword in keywords:
        if len(keyword) >= 2 and keyword.isupper() and keyword.isalpha():
            return True

    return False


def load_methods_with_keywords(conn) -> List[Dict]:
    """Load all methods that have keywords defined."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, name, keywords
        FROM methods
        WHERE keywords IS NOT NULL AND keywords != ''
        ORDER BY id
    """)

    methods = []
    for row in cur.fetchall():
        # Parse comma-separated keywords
        keywords_list = [k.strip() for k in row["keywords"].split(",") if k.strip()]

        if not keywords_list:
            continue

        methods.append(
            {
                "id": row["id"],
                "name": row["name"],
                "keywords": keywords_list,
                "case_sensitive": is_case_sensitive(row["name"], keywords_list),
            }
        )

    cur.close()
    return methods


def create_keyword_patterns(
    methods: List[Dict],
) -> Tuple[Dict[str, List[Dict]], Dict[str, List[Dict]]]:
    """
    Create lookup structures for keyword matching.

    Returns:
        (case_sensitive_patterns, case_insensitive_patterns)
        Each pattern dict maps keyword -> list of method info
    """
    case_sensitive = defaultdict(list)
    case_insensitive = defaultdict(list)

    for method in methods:
        for keyword in method["keywords"]:
            method_info = {
                "id": method["id"],
                "name": method["name"],
                "keyword": keyword,
                "keyword_len": len(keyword),
            }

            if method["case_sensitive"]:
                case_sensitive[keyword].append(method_info)
            else:
                # Store lowercase version for case-insensitive matching
                case_insensitive[keyword.lower()].append(method_info)

    return dict(case_sensitive), dict(case_insensitive)


def find_matching_methods(
    text: str, case_sensitive_patterns: Dict, case_insensitive_patterns: Dict
) -> Set[int]:
    """
    Find all methods whose keywords appear in the text.

    Implements longest-match priority: if multiple keywords match overlapping text,
    only the longest keyword is counted.

    Args:
        text: The text to search (title + abstract)
        case_sensitive_patterns: Case-sensitive keyword patterns
        case_insensitive_patterns: Case-insensitive keyword patterns

    Returns:
        Set of method IDs that match
    """
    if not text:
        return set()

    matched_methods = set()
    matched_positions = set()  # Track which character positions we've already matched

    # Store all potential matches with their positions
    all_matches = []

    # Find case-sensitive matches
    for keyword, method_list in case_sensitive_patterns.items():
        # Use word boundary matching for better accuracy
        # Match whole words or keywords that are part of compound words
        for match in re.finditer(r"\b" + re.escape(keyword) + r"\b", text):
            start, end = match.span()
            for method_info in method_list:
                all_matches.append(
                    {
                        "start": start,
                        "end": end,
                        "length": end - start,
                        "method_id": method_info["id"],
                        "keyword": keyword,
                    }
                )

    # Find case-insensitive matches
    text_lower = text.lower()
    for keyword_lower, method_list in case_insensitive_patterns.items():
        for match in re.finditer(r"\b" + re.escape(keyword_lower) + r"\b", text_lower):
            start, end = match.span()
            for method_info in method_list:
                all_matches.append(
                    {
                        "start": start,
                        "end": end,
                        "length": end - start,
                        "method_id": method_info["id"],
                        "keyword": keyword_lower,
                    }
                )

    # Sort matches by length (longest first), then by position
    all_matches.sort(key=lambda x: (-x["length"], x["start"]))

    # Apply longest-match rule: only keep matches that don't overlap with longer matches
    for match in all_matches:
        match_positions = set(range(match["start"], match["end"]))

        # Check if this match overlaps with any already-accepted match
        if not match_positions.intersection(matched_positions):
            matched_methods.add(match["method_id"])
            matched_positions.update(match_positions)

    return matched_methods


def link_papers_by_keywords():
    """Main function to link papers to methods based on keyword matching."""

    try:
        print("=" * 80)
        print("Linking Papers to Methods Based on Keywords")
        print("=" * 80)

        # Connect to database
        conn = psycopg2.connect(
            database="paperswithcode_hf",
            user="postgres",
            password="postgres",
            host="localhost",
            port="5432",
        )

        # Load methods and create keyword patterns
        print("\n1. Loading methods with keywords...")
        methods = load_methods_with_keywords(conn)
        print(f"   ✓ Loaded {len(methods)} methods with keywords")

        case_sensitive_count = sum(1 for m in methods if m["case_sensitive"])
        case_insensitive_count = len(methods) - case_sensitive_count
        print(f"   - {case_sensitive_count} methods use case-sensitive matching")
        print(f"   - {case_insensitive_count} methods use case-insensitive matching")

        print("\n2. Building keyword patterns...")
        case_sensitive_patterns, case_insensitive_patterns = create_keyword_patterns(
            methods
        )
        total_keywords = len(case_sensitive_patterns) + len(case_insensitive_patterns)
        print(f"   ✓ Built patterns for {total_keywords} unique keywords")
        print(f"   - {len(case_sensitive_patterns)} case-sensitive keywords")
        print(f"   - {len(case_insensitive_patterns)} case-insensitive keywords")

        # Check current state of paper_methods
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) as count FROM paper_methods")
        initial_count = cur.fetchone()["count"]
        print(f"\n3. Current paper_methods relationships: {initial_count:,}")

        # Process papers in batches
        print("\n4. Processing papers...")
        print("   (Streaming through papers and matching keywords...)")

        cur.execute("""
            SELECT id, title, abstract
            FROM papers
            WHERE is_latest_version = true
            ORDER BY id
        """)

        papers_processed = 0
        papers_matched = 0
        new_relationships = 0
        batch = []
        batch_size = 1000

        # Track some statistics
        method_match_counts = defaultdict(int)

        for paper in cur:
            papers_processed += 1

            if papers_processed % 5000 == 0:
                print(
                    f"   Processed {papers_processed:,} papers, "
                    f"matched {papers_matched:,}, "
                    f"found {new_relationships:,} new relationships..."
                )

            # Combine title and abstract for matching
            text = ""
            if paper["title"]:
                text = paper["title"]
            if paper["abstract"]:
                text += " " + paper["abstract"]

            if not text.strip():
                continue

            # Find matching methods
            matching_method_ids = find_matching_methods(
                text, case_sensitive_patterns, case_insensitive_patterns
            )

            if matching_method_ids:
                papers_matched += 1

                for method_id in matching_method_ids:
                    batch.append({"paper_id": paper["id"], "method_id": method_id})
                    new_relationships += 1
                    method_match_counts[method_id] += 1

            # Insert batch
            if len(batch) >= batch_size:
                cur2 = conn.cursor()
                execute_batch(
                    cur2,
                    """
                    INSERT INTO paper_methods (paper_id, method_id)
                    VALUES (%(paper_id)s, %(method_id)s)
                    ON CONFLICT (paper_id, method_id) DO NOTHING
                """,
                    batch,
                )
                conn.commit()
                cur2.close()
                batch = []

        # Insert remaining batch
        if batch:
            cur2 = conn.cursor()
            execute_batch(
                cur2,
                """
                INSERT INTO paper_methods (paper_id, method_id)
                VALUES (%(paper_id)s, %(method_id)s)
                ON CONFLICT (paper_id, method_id) DO NOTHING
            """,
                batch,
            )
            conn.commit()
            cur2.close()

        cur.close()

        # Final statistics
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) as count FROM paper_methods")
        final_count = cur.fetchone()["count"]

        print(f"\n   ✓ Finished processing {papers_processed:,} papers")

        print("\n" + "=" * 80)
        print("Import Statistics")
        print("=" * 80)
        print(f"Papers processed:              {papers_processed:>10,}")
        print(f"Papers with keyword matches:   {papers_matched:>10,}")
        print(f"New relationships found:       {new_relationships:>10,}")
        print(f"Initial paper_methods count:   {initial_count:>10,}")
        print(f"Final paper_methods count:     {final_count:>10,}")
        print(f"Relationships actually added:  {final_count - initial_count:>10,}")

        # Show top methods by new matches
        print("\n" + "=" * 80)
        print("Top 20 Methods by New Keyword Matches")
        print("=" * 80)

        # Get method names for the matched IDs
        method_id_to_name = {}
        for method in methods:
            method_id_to_name[method["id"]] = method["name"]

        # Sort by match count
        sorted_methods = sorted(
            method_match_counts.items(), key=lambda x: x[1], reverse=True
        )[:20]

        for method_id, count in sorted_methods:
            method_name = method_id_to_name.get(method_id, f"Unknown (ID {method_id})")
            print(f"{method_name:30} {count:>8,} matches")

        # Show overall top methods in database
        print("\n" + "=" * 80)
        print("Top 20 Methods by Total Paper Count (after keyword linking)")
        print("=" * 80)

        cur.execute("""
            SELECT m.name, COUNT(pm.paper_id) as paper_count
            FROM methods m
            LEFT JOIN paper_methods pm ON m.id = pm.method_id
            GROUP BY m.id, m.name
            ORDER BY paper_count DESC
            LIMIT 20
        """)

        for row in cur.fetchall():
            print(f"{row['name']:30} {row['paper_count']:>8,} papers")

        cur.close()
        conn.close()

        print("\n✅ Successfully linked papers to methods based on keywords!")

    except Exception as e:
        print(f"\n❌ Error linking papers by keywords: {str(e)}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(link_papers_by_keywords())
