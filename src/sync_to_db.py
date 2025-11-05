"""
Database Sync Script for Form Processing Pipeline
Syncs merged forms from JSON to Railway PostgreSQL
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import Json, execute_values

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # noqa: E402

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class FormDatabaseSync:
    """Sync forms to PostgreSQL database"""

    def __init__(self, database_url: str | None = None):
        """
        Initialize database connection

        Args:
            database_url: PostgreSQL connection string (from Railway)
                         Format: postgresql://user:password@host:port/database
        """
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise ValueError("DATABASE_URL not found in environment variables")

        self.conn = None
        self.cursor = None

    def connect(self):
        """Establish database connection"""
        try:
            logger.info("Connecting to PostgreSQL database...")
            self.conn = psycopg2.connect(self.database_url)
            self.cursor = self.conn.cursor()
            logger.info("✓ Connected successfully")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def disconnect(self):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")

    def initialize_schema(self, schema_file: Path | None = None):
        """
        Initialize database schema from SQL file

        Args:
            schema_file: Path to schema.sql file
        """
        if schema_file is None:
            schema_file = Path(__file__).parent.parent / "db" / "schema.sql"

        if not schema_file.exists():
            logger.warning(f"Schema file not found: {schema_file}")
            return

        try:
            logger.info(f"Initializing schema from {schema_file}...")
            with open(schema_file, "r", encoding="utf-8") as f:
                schema_sql = f.read()

            self.cursor.execute(schema_sql)
            self.conn.commit()
            logger.info("✓ Schema initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize schema: {e}")
            self.conn.rollback()
            raise

    def upsert_form(self, form: Dict[str, Any]):
        """
        Upsert a single form and its fields

        Args:
            form: Form dictionary from all_forms.json
        """
        form_id = form.get("form_id")
        if not form_id:
            logger.warning(f"Form missing form_id, skipping: {form.get('title', 'Unknown')}")
            return

        try:
            # Upsert form metadata
            self.cursor.execute(
                """
                INSERT INTO forms (form_id, title, aliases, source, metadata)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (form_id)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    aliases = EXCLUDED.aliases,
                    source = EXCLUDED.source,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
            """,
                (
                    form_id,
                    form.get("title", ""),
                    form.get("aliases", []),
                    form.get("source", "manual"),
                    Json(form.get("metadata", {})),
                ),
            )

            # Delete existing fields for this form (to handle field removal)
            self.cursor.execute("DELETE FROM form_fields WHERE form_id = %s", (form_id,))

            # Insert fields
            fields = form.get("fields", [])
            if fields:
                field_values = []
                for idx, field in enumerate(fields):
                    field_values.append(
                        (
                            form_id,
                            field.get("name", ""),
                            field.get("label", ""),
                            field.get("type", "string"),
                            field.get("required", False),
                            Json(field.get("validators", {})),
                            Json(field.get("normalizers", [])),
                            field.get("pattern"),
                            idx,  # field_order
                        )
                    )

                execute_values(
                    self.cursor,
                    """
                    INSERT INTO form_fields
                    (form_id, name, label, type, required, validators, normalizers, pattern, field_order)
                    VALUES %s
                    """,
                    field_values,
                )

            logger.info(f"✓ Upserted form: {form_id} ({len(fields)} fields)")

        except Exception as e:
            logger.error(f"Failed to upsert form {form_id}: {e}")
            raise

    def sync_forms(self, forms_file: Path | None = None):
        """
        Sync all forms from JSON file to database

        Args:
            forms_file: Path to all_forms.json (default: forms/all_forms.json)
        """
        if forms_file is None:
            forms_file = Path(__file__).parent.parent / "forms" / "all_forms.json"

        if not forms_file.exists():
            logger.error(f"Forms file not found: {forms_file}")
            raise FileNotFoundError(f"Forms file not found: {forms_file}")

        try:
            logger.info(f"Loading forms from {forms_file}...")
            with open(forms_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            forms = data.get("forms", [])
            logger.info(f"Found {len(forms)} forms to sync")

            # Sync each form
            success_count = 0
            for form in forms:
                try:
                    self.upsert_form(form)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to sync form: {e}")
                    continue

            # Commit all changes
            self.conn.commit()

            logger.info(f"\n✅ Sync completed successfully:")
            logger.info(f"   - Total forms: {len(forms)}")
            logger.info(f"   - Synced: {success_count}")
            logger.info(f"   - Failed: {len(forms) - success_count}")

            # Show database stats
            self.show_stats()

        except Exception as e:
            logger.error(f"Failed to sync forms: {e}")
            self.conn.rollback()
            raise

    def show_stats(self):
        """Show database statistics"""
        try:
            # Count forms by source
            self.cursor.execute(
                """
                SELECT source, COUNT(*) as count
                FROM forms
                GROUP BY source
                ORDER BY source
            """
            )
            stats = self.cursor.fetchall()

            logger.info("\nDatabase statistics:")
            total = 0
            for source, count in stats:
                logger.info(f"   - {source}: {count} forms")
                total += count
            logger.info(f"   - Total: {total} forms")

            # Count total fields
            self.cursor.execute("SELECT COUNT(*) FROM form_fields")
            field_count = self.cursor.fetchone()[0]
            logger.info(f"   - Total fields: {field_count}")

        except Exception as e:
            logger.warning(f"Failed to show stats: {e}")

    def test_search(self, query: str = "đơn"):
        """
        Test search function

        Args:
            query: Search query in Vietnamese
        """
        try:
            logger.info(f"\nTesting search with query: '{query}'")
            self.cursor.execute("SELECT * FROM search_forms(%s, 0.3, 5)", (query,))
            results = self.cursor.fetchall()

            logger.info(f"Found {len(results)} results:")
            for idx, (form_id, title, aliases, source, relevance) in enumerate(results, 1):
                logger.info(f"  {idx}. {title}")
                logger.info(f"     Score: {relevance:.3f} | Source: {source} | ID: {form_id}")

        except Exception as e:
            logger.error(f"Search test failed: {e}")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Sync forms to PostgreSQL database")
    parser.add_argument("--init-schema", action="store_true", help="Initialize database schema (run first time)")
    parser.add_argument("--forms-file", type=Path, help="Path to forms JSON file (default: forms/all_forms.json)")
    parser.add_argument("--test-search", type=str, help="Test search with query")
    parser.add_argument("--database-url", type=str, help="PostgreSQL connection URL (default: from DATABASE_URL env)")

    args = parser.parse_args()

    # Initialize sync
    sync = FormDatabaseSync(database_url=args.database_url)

    try:
        # Connect to database
        sync.connect()

        # Initialize schema if requested
        if args.init_schema:
            sync.initialize_schema()

        # Sync forms
        sync.sync_forms(forms_file=args.forms_file)

        # Test search if requested
        if args.test_search:
            sync.test_search(query=args.test_search)

    except Exception as e:
        logger.error(f"Sync failed: {e}", exc_info=True)
        sys.exit(1)

    finally:
        sync.disconnect()


if __name__ == "__main__":
    main()
