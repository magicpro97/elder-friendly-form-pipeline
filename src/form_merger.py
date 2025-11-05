#!/usr/bin/env python3
"""
Form Merger - Merge manual and crawled forms, remove duplicates

Features:
- Load forms from multiple sources
- Deduplicate based on title similarity
- Merge aliases and metadata
- Prioritize manual forms over crawled
- Generate merged index
"""

import json
import logging
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FormMerger:
    """Merge manual and crawled forms with deduplication"""

    def __init__(
        self,
        manual_forms_path: str = "forms/form_samples.json",
        crawled_forms_dir: str = "forms/crawled_forms",
        output_path: str = "forms/all_forms.json",
    ):
        self.manual_forms_path = Path(manual_forms_path)
        self.crawled_forms_dir = Path(crawled_forms_dir)
        self.output_path = Path(output_path)

        self.similarity_threshold = 0.8  # 80% similarity = duplicate

    def load_manual_forms(self) -> list[dict[str, Any]]:
        """Load manually created forms from form_samples.json"""
        if not self.manual_forms_path.exists():
            logger.warning(f"Manual forms file not found: {self.manual_forms_path}")
            return []

        try:
            with open(self.manual_forms_path, encoding="utf-8") as f:
                data = json.load(f)
                forms = data.get("forms", [])

            # Mark as manual source
            for form in forms:
                if "source" not in form:
                    form["source"] = "manual"

            logger.info(f"Loaded {len(forms)} manual forms")
            return forms

        except Exception as e:
            logger.error(f"Failed to load manual forms: {e}")
            return []

    def load_crawled_forms(self) -> list[dict[str, Any]]:
        """Load crawled forms from individual JSON files"""
        if not self.crawled_forms_dir.exists():
            logger.warning(f"Crawled forms directory not found: {self.crawled_forms_dir}")
            return []

        forms = []
        for json_file in self.crawled_forms_dir.glob("*.json"):
            if json_file.name.startswith("_"):  # Skip index files
                continue

            try:
                with open(json_file, encoding="utf-8") as f:
                    form = json.load(f)
                    forms.append(form)
            except Exception as e:
                logger.error(f"Failed to load {json_file.name}: {e}")

        logger.info(f"Loaded {len(forms)} crawled forms")
        return forms

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two texts using SequenceMatcher

        Returns:
            Similarity score from 0.0 to 1.0
        """
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

    def is_duplicate(self, form1: dict[str, Any], form2: dict[str, Any]) -> bool:
        """
        Check if two forms are duplicates based on title similarity

        Args:
            form1: First form
            form2: Second form

        Returns:
            True if forms are considered duplicates
        """
        title1 = form1.get("title", "").lower()
        title2 = form2.get("title", "").lower()

        # Direct comparison
        if title1 == title2:
            return True

        # Similarity-based comparison
        similarity = self.calculate_similarity(title1, title2)
        if similarity >= self.similarity_threshold:
            logger.info(f"Duplicate found: '{title1}' ≈ '{title2}' (similarity: {similarity:.2f})")
            return True

        # Check aliases
        aliases1 = set(alias.lower() for alias in form1.get("aliases", []))
        aliases2 = set(alias.lower() for alias in form2.get("aliases", []))

        if aliases1 & aliases2:  # Intersection
            logger.info(f"Duplicate found via aliases: {aliases1 & aliases2}")
            return True

        return False

    def merge_form_metadata(self, manual: dict[str, Any], crawled: dict[str, Any]) -> dict[str, Any]:
        """
        Merge metadata from crawled form into manual form

        Priority: Manual form takes precedence, but we preserve crawled metadata
        """
        merged = manual.copy()

        # Merge aliases (keep unique)
        manual_aliases = set(manual.get("aliases", []))
        crawled_aliases = set(crawled.get("aliases", []))
        merged["aliases"] = list(manual_aliases | crawled_aliases)

        # Add crawled metadata
        if "metadata" not in merged:
            merged["metadata"] = {}

        merged["metadata"]["has_crawled_version"] = True
        merged["metadata"]["crawled_source"] = crawled.get("metadata", {})

        logger.info(f"Merged: '{manual.get('title')}' + crawled version")
        return merged

    def deduplicate_forms(
        self, manual_forms: list[dict[str, Any]], crawled_forms: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Deduplicate forms, prioritizing manual over crawled

        Strategy:
        1. Keep all manual forms
        2. For each crawled form:
           - If duplicate of manual form → merge metadata
           - If unique → add to list

        Returns:
            Deduplicated list of forms
        """
        merged_forms = manual_forms.copy()
        added_count = 0
        merged_count = 0

        for crawled in crawled_forms:
            is_dup = False

            # Check against all manual forms
            for i, manual in enumerate(merged_forms):
                if manual.get("source") != "manual":
                    continue

                if self.is_duplicate(manual, crawled):
                    # Merge metadata into manual form
                    merged_forms[i] = self.merge_form_metadata(manual, crawled)
                    merged_count += 1
                    is_dup = True
                    break

            if not is_dup:
                # Unique crawled form, add it
                merged_forms.append(crawled)
                added_count += 1

        logger.info("Deduplication complete:")
        logger.info(f"  - Manual forms: {len(manual_forms)}")
        logger.info(f"  - Crawled forms: {len(crawled_forms)}")
        logger.info(f"  - Merged metadata: {merged_count}")
        logger.info(f"  - Added unique: {added_count}")
        logger.info(f"  - Total forms: {len(merged_forms)}")

        return merged_forms

    def merge(self) -> list[dict[str, Any]]:
        """
        Main merge function

        Returns:
            Merged and deduplicated forms
        """
        logger.info("Starting form merge...")

        # Load forms
        manual_forms = self.load_manual_forms()
        crawled_forms = self.load_crawled_forms()

        if not manual_forms and not crawled_forms:
            logger.warning("No forms found to merge")
            return []

        # Deduplicate
        merged_forms = self.deduplicate_forms(manual_forms, crawled_forms)

        # Save merged forms
        self.save_merged_forms(merged_forms)

        return merged_forms

    def save_merged_forms(self, forms: list[dict[str, Any]]) -> None:
        """
        Save merged forms to output file

        Args:
            forms: List of merged forms
        """
        output_data = {
            "forms": forms,
            "count": len(forms),
            "sources": {
                "manual": len([f for f in forms if f.get("source") == "manual"]),
                "crawler": len([f for f in forms if f.get("source") == "crawler"]),
            },
            "generated_at": datetime.now().isoformat() if self.output_path.exists() else None,
        }

        # Ensure output directory exists
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved merged forms: {self.output_path}")
        logger.info(f"  - Total: {len(forms)} forms")
        logger.info(f"  - Manual: {output_data['sources']['manual']}")
        logger.info(f"  - Crawler: {output_data['sources']['crawler']}")


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Merge manual and crawled forms")
    parser.add_argument("--manual", "-m", default="forms/form_samples.json", help="Manual forms JSON file")
    parser.add_argument("--crawled", "-c", default="forms/crawled_forms", help="Crawled forms directory")
    parser.add_argument("--output", "-o", default="forms/all_forms.json", help="Output merged file")
    parser.add_argument("--threshold", "-t", type=float, default=0.8, help="Similarity threshold (0.0-1.0)")

    args = parser.parse_args()

    merger = FormMerger(
        manual_forms_path=args.manual,
        crawled_forms_dir=args.crawled,
        output_path=args.output,
    )
    merger.similarity_threshold = args.threshold

    merged_forms = merger.merge()

    print(f"\n{'='*60}")
    print("Merge complete!")
    print(f"{'='*60}")
    print(f"Output: {args.output}")
    print(f"Total forms: {len(merged_forms)}")


if __name__ == "__main__":
    main()
