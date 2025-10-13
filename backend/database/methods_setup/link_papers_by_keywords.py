#!/usr/bin/env python3
"""
Link papers to methods based on keyword matching in titles and abstracts.

Case-Sensitivity Rules:
- If a keyword contains at least 1 capital letter: case-sensitive matching
- If a keyword is all lowercase: case-insensitive matching
- Examples:
  - "BERT", "GPT-4", "ResNet" → case-sensitive (must match exactly)
  - "transformer", "attention", "dropout" → case-insensitive (any case)
  - "vision-language" → case-insensitive (all lowercase)
  - "ViT", "BigGAN" → case-sensitive (has capital letters)

Matching Strategy:
1. Only match methods that have keywords defined
2. Use word boundary matching for accuracy
3. Prefer longest matching keyword (e.g., GPT-2 over GPT)
"""

import re
from typing import Dict, List, Set, Tuple
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch


def is_case_sensitive_keyword(keyword: str) -> bool:
    """
    Determine if a keyword should use case-sensitive matching.

    Rule: If a keyword contains at least 1 capital letter, it's case-sensitive.
          If keyword is all lowercase, it's case-insensitive.

    Args:
        keyword: The keyword to check

    Returns:
        True if case-sensitive matching should be used
    """
    # Check if keyword has at least one uppercase letter
    return any(c.isupper() for c in keyword)


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

        # Categorize keywords by case sensitivity
        case_sensitive_keywords = []
        case_insensitive_keywords = []

        for keyword in keywords_list:
            if is_case_sensitive_keyword(keyword):
                case_sensitive_keywords.append(keyword)
            else:
                case_insensitive_keywords.append(keyword)

        methods.append(
            {
                "id": row["id"],
                "name": row["name"],
                "keywords": keywords_list,
                "case_sensitive_keywords": case_sensitive_keywords,
                "case_insensitive_keywords": case_insensitive_keywords,
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
        method_id = method["id"]

        # Add case-sensitive keywords
        for keyword in method["case_sensitive_keywords"]:
            method_info = {
                "id": method_id,
                "name": method["name"],
                "keyword": keyword,
                "keyword_len": len(keyword),
            }
            case_sensitive[keyword].append(method_info)

        # Add case-insensitive keywords (store in lowercase)
        for keyword in method["case_insensitive_keywords"]:
            method_info = {
                "id": method_id,
                "name": method["name"],
                "keyword": keyword,
                "keyword_len": len(keyword),
            }
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

        # Count keywords by case sensitivity
        total_case_sensitive = sum(len(m["case_sensitive_keywords"]) for m in methods)
        total_case_insensitive = sum(
            len(m["case_insensitive_keywords"]) for m in methods
        )
        print(f"   - {total_case_sensitive} case-sensitive keywords")
        print(f"   - {total_case_insensitive} case-insensitive keywords")

        print("\n2. Building keyword patterns...")
        case_sensitive_patterns, case_insensitive_patterns = create_keyword_patterns(
            methods
        )
        total_keywords = len(case_sensitive_patterns) + len(case_insensitive_patterns)
        print(f"   ✓ Built patterns for {total_keywords} unique keywords")
        print(f"   - {len(case_sensitive_patterns)} unique case-sensitive keywords")
        print(f"   - {len(case_insensitive_patterns)} unique case-insensitive keywords")

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
