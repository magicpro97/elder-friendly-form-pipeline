"""
Form Repository - PostgreSQL data access layer
Provides form queries for the FastAPI app
"""

import logging
import os
from typing import Any, Dict, List, Optional

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

logger = logging.getLogger(__name__)


class FormRepository:
    """Repository for accessing forms from PostgreSQL"""

    def __init__(self, database_url: str | None = None):
        """
        Initialize repository with database connection

        Args:
            database_url: PostgreSQL connection string (from Railway)
        """
        self.database_url = database_url or os.getenv("DATABASE_URL")
        self._conn = None
        self._form_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_enabled = True

    def _get_connection(self):
        """Get or create database connection with auto-reconnect"""
        if self._conn is None or self._conn.closed:
            try:
                self._conn = psycopg2.connect(self.database_url, cursor_factory=RealDictCursor, connect_timeout=5)
                logger.info("Connected to PostgreSQL database")
            except Exception as e:
                logger.error(f"Failed to connect to database: {e}")
                raise
        return self._conn

    def close(self):
        """Close database connection"""
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.info("Closed database connection")

    def get_all_forms(self, source: str | None = None) -> List[Dict[str, Any]]:
        """
        Get all forms, optionally filtered by source

        Args:
            source: Filter by source ('manual' or 'crawler')

        Returns:
            List of form dictionaries with fields
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Build query
            if source:
                query = """
                    SELECT f.*,
                           ARRAY_AGG(
                               json_build_object(
                                   'name', ff.name,
                                   'label', ff.label,
                                   'type', ff.type,
                                   'required', ff.required,
                                   'validators', ff.validators,
                                   'normalizers', ff.normalizers,
                                   'pattern', ff.pattern
                               ) ORDER BY ff.field_order
                           ) FILTER (WHERE ff.id IS NOT NULL) as fields
                    FROM forms f
                    LEFT JOIN form_fields ff ON f.form_id = ff.form_id
                    WHERE f.source = %s
                    GROUP BY f.form_id
                    ORDER BY f.title
                """
                cursor.execute(query, (source,))
            else:
                query = """
                    SELECT f.*,
                           ARRAY_AGG(
                               json_build_object(
                                   'name', ff.name,
                                   'label', ff.label,
                                   'type', ff.type,
                                   'required', ff.required,
                                   'validators', ff.validators,
                                   'normalizers', ff.normalizers,
                                   'pattern', ff.pattern
                               ) ORDER BY ff.field_order
                           ) FILTER (WHERE ff.id IS NOT NULL) as fields
                    FROM forms f
                    LEFT JOIN form_fields ff ON f.form_id = ff.form_id
                    GROUP BY f.form_id
                    ORDER BY f.title
                """
                cursor.execute(query)

            results = cursor.fetchall()
            cursor.close()

            # Convert to list of dicts
            forms = []
            for row in results:
                form = dict(row)
                # Ensure fields is a list (not None)
                if form["fields"] is None:
                    form["fields"] = []
                forms.append(form)

            logger.info(f"Retrieved {len(forms)} forms from database" + (f" (source={source})" if source else ""))
            return forms

        except Exception as e:
            logger.error(f"Failed to get forms: {e}")
            raise

    def get_form_by_id(self, form_id: str) -> Optional[Dict[str, Any]]:
        """
        Get form by ID with fields

        Args:
            form_id: Form ID to retrieve

        Returns:
            Form dictionary with fields, or None if not found
        """
        # Check cache first
        if self._cache_enabled and form_id in self._form_cache:
            logger.debug(f"Cache hit for form {form_id}")
            return self._form_cache[form_id]

        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT f.*,
                       ARRAY_AGG(
                           json_build_object(
                               'name', ff.name,
                               'label', ff.label,
                               'type', ff.type,
                               'required', ff.required,
                               'validators', ff.validators,
                               'normalizers', ff.normalizers,
                               'pattern', ff.pattern
                           ) ORDER BY ff.field_order
                       ) FILTER (WHERE ff.id IS NOT NULL) as fields
                FROM forms f
                LEFT JOIN form_fields ff ON f.form_id = ff.form_id
                WHERE f.form_id = %s
                GROUP BY f.form_id
            """,
                (form_id,),
            )

            result = cursor.fetchone()
            cursor.close()

            if result:
                form = dict(result)
                # Ensure fields is a list
                if form["fields"] is None:
                    form["fields"] = []

                # Update cache
                if self._cache_enabled:
                    self._form_cache[form_id] = form

                logger.debug(f"Retrieved form {form_id} from database")
                return form

            logger.warning(f"Form {form_id} not found")
            return None

        except Exception as e:
            logger.error(f"Failed to get form {form_id}: {e}")
            raise

    def search_forms(self, query: str, min_similarity: float = 0.3, max_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search forms using Vietnamese-aware search function

        Args:
            query: Search query in Vietnamese
            min_similarity: Minimum similarity threshold (0.0-1.0)
            max_results: Maximum number of results

        Returns:
            List of forms with relevance scores
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM search_forms(%s, %s, %s)", (query, min_similarity, max_results))

            results = cursor.fetchall()
            cursor.close()

            # Convert to list of dicts with relevance score
            forms = []
            for row in results:
                form = {
                    "form_id": row["form_id"],
                    "title": row["title"],
                    "aliases": row["aliases"],
                    "source": row["source"],
                    "relevance": float(row["relevance"]),
                }
                forms.append(form)

            logger.info(f"Search '{query}' returned {len(forms)} results")
            return forms

        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            raise

    def get_form_index(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all forms as a dictionary indexed by form_id

        Returns:
            Dictionary of {form_id: form_data}
        """
        forms = self.get_all_forms()
        return {form["form_id"]: form for form in forms}

    def get_aliases_map(self) -> Dict[str, str]:
        """
        Get mapping of aliases to form_ids

        Returns:
            Dictionary of {alias: form_id}
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT form_id, unnest(aliases) as alias
                FROM forms
                WHERE aliases IS NOT NULL AND array_length(aliases, 1) > 0
            """
            )

            results = cursor.fetchall()
            cursor.close()

            # Build aliases map
            aliases = {}
            for row in results:
                aliases[row["alias"].lower()] = row["form_id"]

            logger.debug(f"Built aliases map with {len(aliases)} entries")
            return aliases

        except Exception as e:
            logger.error(f"Failed to get aliases map: {e}")
            raise

    def clear_cache(self):
        """Clear the form cache"""
        self._form_cache.clear()
        logger.info("Form cache cleared")


# Singleton instance
_repository: Optional[FormRepository] = None


def get_form_repository() -> FormRepository:
    """
    Get singleton form repository instance

    Returns:
        FormRepository instance
    """
    global _repository
    if _repository is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            logger.warning("DATABASE_URL not set, form repository unavailable")
            raise ValueError("DATABASE_URL not configured")
        _repository = FormRepository(database_url)
    return _repository


def close_repository():
    """Close repository connection (call on app shutdown)"""
    global _repository
    if _repository:
        _repository.close()
        _repository = None
