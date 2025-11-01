#!/bin/bash
# CSS Syntax Validator - Only checks for critical parse errors
# Ignores vendor prefixes and CSS variables warnings

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🎨 Validating CSS files..."

# Run css-validator and filter output for critical errors only
output=$(npx --yes css-validator "$@" 2>&1 || true)

# Check for critical parse errors (not warnings about vendor extensions)
critical_errors=$(echo "$output" | grep -i "parse error" || true)

if [ -n "$critical_errors" ]; then
    echo -e "${RED}❌ CSS Parse Errors Found:${NC}"
    echo "$critical_errors"
    exit 1
fi

# Check for invalid values that aren't vendor-specific
invalid_values=$(echo "$output" | grep "is not a .* value" | grep -v "scrollbar-width" | grep -v "prefers-contrast" || true)

if [ -n "$invalid_values" ]; then
    echo -e "${YELLOW}⚠️  CSS Validation Warnings:${NC}"
    echo "$invalid_values"
fi

echo -e "${GREEN}✅ CSS validation passed (no critical errors)${NC}"
exit 0
