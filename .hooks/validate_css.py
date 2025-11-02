#!/usr/bin/env python3
"""
Cross-platform CSS validator for pre-commit hooks.
Performs basic CSS syntax validation without external dependencies.
"""

import re
import sys
from pathlib import Path


def validate_css_file(filepath: str) -> tuple[bool, list[str]]:
    """
    Validate CSS file for basic syntax errors.

    Args:
        filepath: Path to CSS file

    Returns:
        Tuple of (is_valid, errors)
    """
    errors = []

    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return False, [f"Failed to read file: {e}"]

    # Remove comments to avoid false positives
    content_no_comments = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)

    # Check for basic syntax errors

    # 1. Unmatched braces
    open_braces = content_no_comments.count("{")
    close_braces = content_no_comments.count("}")
    if open_braces != close_braces:
        errors.append(f"Unmatched braces: {open_braces} opening {{ vs {close_braces} closing }}")

    # 2. Unmatched parentheses in calc() or other functions
    open_parens = content_no_comments.count("(")
    close_parens = content_no_comments.count(")")
    if open_parens != close_parens:
        errors.append(f"Unmatched parentheses: {open_parens} opening ( vs {close_parens} closing )")

    # 3. Check for invalid property syntax (basic check)
    # Look for lines that should be properties but don't have colon
    lines = content_no_comments.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip empty lines, comments, selectors, media queries, keyframes
        if not stripped or stripped.startswith("@") or stripped.endswith("{") or stripped == "}":
            continue

        # If line is inside a rule block and contains alphanumeric but no colon, likely error
        if re.match(r"^\w+[\w-]*\s+[^:;{}\s]", stripped) and ":" not in stripped and ";" not in stripped:
            errors.append(f"Line {i}: Possible missing colon in property declaration: '{stripped[:50]}'")

    # 4. Check for unclosed strings
    # Simple check: count quotes outside of comments
    single_quotes = content_no_comments.count("'")
    double_quotes = content_no_comments.count('"')
    if single_quotes % 2 != 0:
        errors.append(f"Unclosed single quote (') - found {single_quotes} single quotes")
    if double_quotes % 2 != 0:
        errors.append(f'Unclosed double quote (") - found {double_quotes} double quotes')

    # 5. Check for duplicate properties (common mistake)
    # Extract rule blocks and check for duplicate properties
    rule_blocks = re.findall(r"\{([^{}]+)\}", content_no_comments)
    for block in rule_blocks:
        properties = {}
        for line in block.split(";"):
            if ":" in line:
                prop = line.split(":")[0].strip()
                if prop and not prop.startswith("@"):  # Ignore at-rules
                    if prop in properties:
                        # This is a warning, not a critical error (CSS uses last declaration)
                        pass  # Could add to warnings list if needed
                    properties[prop] = True

    return len(errors) == 0, errors


def main():
    """Main entry point for pre-commit hook."""
    if len(sys.argv) < 2:
        print("Usage: validate_css.py <file1.css> [file2.css ...]")  # noqa: T201
        sys.exit(1)

    all_valid = True
    total_files = len(sys.argv) - 1

    print(f"Validating {total_files} CSS file(s)...")  # noqa: T201

    for filepath in sys.argv[1:]:
        if not Path(filepath).exists():
            print(f"[FAIL] File not found: {filepath}")  # noqa: T201
            all_valid = False
            continue

        is_valid, errors = validate_css_file(filepath)

        if not is_valid:
            print(f"\n[FAIL] {filepath}:")  # noqa: T201
            for error in errors:
                print(f"   * {error}")  # noqa: T201
            all_valid = False
        else:
            print(f"[PASS] {filepath}")  # noqa: T201

    if all_valid:
        print(f"\n[SUCCESS] All {total_files} CSS file(s) passed validation!")  # noqa: T201
        sys.exit(0)
    else:
        print("\n[ERROR] CSS validation failed!")  # noqa: T201
        sys.exit(1)


if __name__ == "__main__":
    main()
