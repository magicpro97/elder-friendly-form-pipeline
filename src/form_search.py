#!/usr/bin/env python3
"""
Form Search - Fuzzy search for Vietnamese forms

Features:
- Search by title, aliases, keywords
- Vietnamese text normalization
- Fuzzy matching with configurable threshold
- Ranking by relevance
- Support for both manual and crawled forms
"""

import json
import logging
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FormSearch:
    """Search engine for Vietnamese forms"""

    def __init__(self, forms_path: str = "forms/all_forms.json"):
        self.forms_path = Path(forms_path)
        self.forms: List[Dict[str, Any]] = []
        self.search_index: Dict[str, List[int]] = {}  # keyword -> form indices

        self.load_forms()
        self.build_index()

    def normalize_vietnamese(self, text: str) -> str:
        """
        Normalize Vietnamese text for searching

        Steps:
        1. Lowercase
        2. Remove diacritics (á → a, đ → d)
        3. Remove special characters
        4. Normalize spaces
        """
        # Lowercase
        text = text.lower()

        # Remove diacritics using unicodedata
        text = unicodedata.normalize("NFD", text)
        text = "".join(char for char in text if unicodedata.category(char) != "Mn")

        # Manual replacements for special Vietnamese characters
        replacements = {"đ": "d", "Đ": "d"}
        for viet, ascii_char in replacements.items():
            text = text.replace(viet, ascii_char)

        # Remove special characters, keep only alphanumeric and spaces
        text = re.sub(r"[^a-z0-9\s]", " ", text)

        # Normalize spaces
        text = " ".join(text.split())

        return text

    def load_forms(self) -> None:
        """Load forms from merged JSON file"""
        if not self.forms_path.exists():
            logger.warning(f"Forms file not found: {self.forms_path}")
            # Fallback to manual forms
            fallback_path = Path("forms/form_samples.json")
            if fallback_path.exists():
                logger.info("Using fallback: form_samples.json")
                self.forms_path = fallback_path
            else:
                self.forms = []
                return

        try:
            with open(self.forms_path, encoding="utf-8") as f:
                data = json.load(f)
                self.forms = data.get("forms", [])

            logger.info(f"Loaded {len(self.forms)} forms from {self.forms_path.name}")

        except Exception as e:
            logger.error(f"Failed to load forms: {e}")
            self.forms = []

    def build_index(self) -> None:
        """
        Build search index for fast keyword lookup

        Index structure:
        {
            "don": [0, 2, 5],  # Form indices
            "xin": [0, 1],
            "viec": [0],
            ...
        }
        """
        self.search_index.clear()

        for idx, form in enumerate(self.forms):
            # Index title
            title = form.get("title", "")
            for word in self.normalize_vietnamese(title).split():
                if word not in self.search_index:
                    self.search_index[word] = []
                if idx not in self.search_index[word]:
                    self.search_index[word].append(idx)

            # Index aliases
            for alias in form.get("aliases", []):
                for word in self.normalize_vietnamese(alias).split():
                    if word not in self.search_index:
                        self.search_index[word] = []
                    if idx not in self.search_index[word]:
                        self.search_index[word].append(idx)

            # Index form_id
            form_id = form.get("form_id", "")
            for word in self.normalize_vietnamese(form_id).split("_"):
                if word not in self.search_index:
                    self.search_index[word] = []
                if idx not in self.search_index[word]:
                    self.search_index[word].append(idx)

        logger.info(f"Built search index with {len(self.search_index)} keywords")

    def calculate_relevance(self, query: str, form: Dict[str, Any]) -> float:
        """
        Calculate relevance score for a form

        Scoring:
        - Exact title match: 1.0
        - Title contains query: 0.8
        - Alias match: 0.7
        - Keyword match: 0.5
        - Fuzzy similarity: 0.0-0.5

        Returns:
            Relevance score from 0.0 to 1.0
        """
        query_normalized = self.normalize_vietnamese(query)
        title = form.get("title", "")
        title_normalized = self.normalize_vietnamese(title)

        # Exact match
        if query_normalized == title_normalized:
            return 1.0

        # Title contains query
        if query_normalized in title_normalized:
            return 0.8

        # Check aliases
        for alias in form.get("aliases", []):
            alias_normalized = self.normalize_vietnamese(alias)
            if query_normalized == alias_normalized:
                return 0.7
            if query_normalized in alias_normalized:
                return 0.6

        # Fuzzy similarity
        similarity = SequenceMatcher(None, query_normalized, title_normalized).ratio()

        # Boost score if query words appear in title
        query_words = set(query_normalized.split())
        title_words = set(title_normalized.split())
        word_overlap = len(query_words & title_words) / len(query_words) if query_words else 0

        # Combined score
        score = max(similarity, word_overlap * 0.5)

        return score

    def search(
        self, query: str, min_score: float = 0.3, max_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search for forms matching query

        Args:
            query: Search query (Vietnamese text)
            min_score: Minimum relevance score (0.0-1.0)
            max_results: Maximum number of results

        Returns:
            List of forms sorted by relevance (highest first)
        """
        if not query or not self.forms:
            return []

        query_normalized = self.normalize_vietnamese(query)
        query_words = query_normalized.split()

        # Step 1: Fast index lookup
        candidate_indices = set()
        for word in query_words:
            if word in self.search_index:
                candidate_indices.update(self.search_index[word])

        # Step 2: Score all forms (index + fuzzy)
        results: List[Tuple[float, Dict[str, Any]]] = []

        # Score candidates from index
        for idx in candidate_indices:
            form = self.forms[idx]
            score = self.calculate_relevance(query, form)
            if score >= min_score:
                results.append((score, form))

        # Also check forms not in index (fuzzy matching)
        for idx, form in enumerate(self.forms):
            if idx not in candidate_indices:
                score = self.calculate_relevance(query, form)
                if score >= min_score:
                    results.append((score, form))

        # Step 3: Sort by score (highest first)
        results.sort(key=lambda x: x[0], reverse=True)

        # Step 4: Return top results with scores
        top_results = []
        for score, form in results[:max_results]:
            form_with_score = form.copy()
            form_with_score["_search_score"] = round(score, 3)
            top_results.append(form_with_score)

        logger.info(f"Search '{query}': {len(top_results)} results (min_score={min_score})")
        return top_results

    def search_by_id(self, form_id: str) -> Dict[str, Any] | None:
        """
        Get form by exact form_id

        Args:
            form_id: Form identifier

        Returns:
            Form dict or None if not found
        """
        for form in self.forms:
            if form.get("form_id") == form_id:
                return form
        return None

    def list_all(self, source: str | None = None) -> List[Dict[str, Any]]:
        """
        List all forms, optionally filtered by source

        Args:
            source: Filter by source ('manual' or 'crawler')

        Returns:
            List of forms
        """
        if source:
            return [f for f in self.forms if f.get("source") == source]
        return self.forms.copy()


def main():
    """CLI entry point for testing"""
    import argparse

    parser = argparse.ArgumentParser(description="Search Vietnamese forms")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--forms", "-f", default="forms/all_forms.json", help="Forms JSON file")
    parser.add_argument("--min-score", "-s", type=float, default=0.3, help="Minimum score")
    parser.add_argument("--max", "-m", type=int, default=10, help="Max results")
    parser.add_argument("--list", action="store_true", help="List all forms")
    parser.add_argument("--source", choices=["manual", "crawler"], help="Filter by source")

    args = parser.parse_args()

    searcher = FormSearch(forms_path=args.forms)

    if args.list:
        forms = searcher.list_all(source=args.source)
        print(f"\nTotal forms: {len(forms)}")
        for i, form in enumerate(forms, 1):
            source = form.get("source", "unknown")
            print(f"{i}. [{source}] {form.get('title')} (id: {form.get('form_id')})")
        return

    if not args.query:
        print("Error: Please provide a search query or use --list")
        parser.print_help()
        return

    # Search
    results = searcher.search(args.query, min_score=args.min_score, max_results=args.max)

    print(f"\nSearch: '{args.query}'")
    print(f"Found: {len(results)} results")
    print("=" * 60)

    for i, form in enumerate(results, 1):
        score = form.get("_search_score", 0.0)
        source = form.get("source", "unknown")
        title = form.get("title", "")
        form_id = form.get("form_id", "")
        aliases = ", ".join(form.get("aliases", [])[:2])

        print(f"\n{i}. {title}")
        print(f"   Score: {score:.3f} | Source: {source} | ID: {form_id}")
        if aliases:
            print(f"   Aliases: {aliases}")


if __name__ == "__main__":
    main()
