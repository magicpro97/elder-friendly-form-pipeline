-- PostgreSQL Schema for Elder-Friendly Form Pipeline
-- Created: 2025-11-05
-- Purpose: Store processed forms from crawler with full-text search support

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- For fuzzy text search

-- Forms table: Main form metadata
CREATE TABLE IF NOT EXISTS forms (
    form_id VARCHAR(255) PRIMARY KEY,
    title TEXT NOT NULL,
    aliases TEXT[] DEFAULT '{}',
    source VARCHAR(50) NOT NULL,  -- 'manual' or 'crawler'
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Form fields table: Individual fields for each form
CREATE TABLE IF NOT EXISTS form_fields (
    id SERIAL PRIMARY KEY,
    form_id VARCHAR(255) NOT NULL REFERENCES forms(form_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    label TEXT NOT NULL,
    type VARCHAR(50) NOT NULL,  -- 'string', 'date', 'phone', 'email', etc.
    required BOOLEAN DEFAULT false,
    validators JSONB DEFAULT '{}',
    normalizers JSONB DEFAULT '[]',
    pattern TEXT,
    field_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_forms_source ON forms(source);
CREATE INDEX IF NOT EXISTS idx_forms_created ON forms(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_form_fields_form_id ON form_fields(form_id);
CREATE INDEX IF NOT EXISTS idx_form_fields_order ON form_fields(form_id, field_order);

-- Full-text search index for Vietnamese text
-- Using 'simple' config to avoid language-specific stemming issues with Vietnamese
-- Removed GIN FTS indexes due to IMMUTABLE function requirement
-- Will use LIKE queries and trigram instead

-- Fuzzy search index using trigram
CREATE INDEX IF NOT EXISTS idx_forms_title_trgm ON forms USING gin(title gin_trgm_ops);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at
DROP TRIGGER IF EXISTS update_forms_updated_at ON forms;
CREATE TRIGGER update_forms_updated_at
    BEFORE UPDATE ON forms
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to search forms with Vietnamese normalization
CREATE OR REPLACE FUNCTION search_forms(
    search_query TEXT,
    min_similarity FLOAT DEFAULT 0.3,
    max_results INTEGER DEFAULT 10
)
RETURNS TABLE (
    form_id VARCHAR,
    title TEXT,
    aliases TEXT[],
    source VARCHAR,
    relevance FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        f.form_id,
        f.title,
        f.aliases,
        f.source,
        GREATEST(
            -- Exact title match
            CASE WHEN LOWER(f.title) = LOWER(search_query) THEN 1.0 ELSE 0.0 END,
            -- Title contains query
            CASE WHEN LOWER(f.title) LIKE '%' || LOWER(search_query) || '%' THEN 0.8 ELSE 0.0 END,
            -- Exact alias match
            CASE WHEN LOWER(search_query) = ANY(SELECT LOWER(unnest(f.aliases))) THEN 0.7 ELSE 0.0 END,
            -- Alias contains query
            CASE WHEN EXISTS(SELECT 1 FROM unnest(f.aliases) a WHERE LOWER(a) LIKE '%' || LOWER(search_query) || '%') THEN 0.6 ELSE 0.0 END,
            -- Trigram similarity
            similarity(f.title, search_query) * 0.5
        ) AS relevance
    FROM forms f
    WHERE
        LOWER(f.title) LIKE '%' || LOWER(search_query) || '%'
        OR LOWER(search_query) = ANY(SELECT LOWER(unnest(f.aliases)))
        OR EXISTS(SELECT 1 FROM unnest(f.aliases) a WHERE LOWER(a) LIKE '%' || LOWER(search_query) || '%')
        OR similarity(f.title, search_query) >= min_similarity
    ORDER BY relevance DESC
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;

-- Comments for documentation
COMMENT ON TABLE forms IS 'Stores form metadata including title, aliases, and source';
COMMENT ON TABLE form_fields IS 'Stores individual fields for each form with validation rules';
COMMENT ON FUNCTION search_forms IS 'Search forms with Vietnamese text normalization and relevance scoring';

-- Initial stats
SELECT
    'Schema created successfully' AS status,
    NOW() AS created_at;
