"""
SQLite storage for clinic facts, approved FAQs, and persistent conversation history.

Zero external dependencies (uses standard library `sqlite3`).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from core.safety_filter import normalize_arabic

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DB_DIR / "clinic.db"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"


class AssistantDatabase:
    """Manages the local SQLite database for the clinic assistant."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.sync_from_knowledge(KNOWLEDGE_DIR)

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Facts table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS clinic_facts (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    category TEXT NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )
            # 2. FAQs table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS faqs (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    question_ar TEXT NOT NULL,
                    answer_ar TEXT NOT NULL,
                    keywords TEXT NOT NULL,
                    approved INTEGER NOT NULL,
                    updated_at TIMESTAMP NOT NULL
                )
                """
            )
            # 3. Persistent conversation history
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_conv_user ON conversation_messages(user_id, id DESC)"
            )
            conn.commit()

    def sync_from_knowledge(self, knowledge_dir: Path | str = KNOWLEDGE_DIR) -> None:
        """Sync YAML profile and JSON FAQs into SQLite tables."""
        kdir = Path(knowledge_dir)
        profile_path = kdir / "doctor_profile.yaml"
        faqs_path = kdir / "faqs.json"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc).isoformat()

            # Sync Profile
            if profile_path.is_file():
                profile_data = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
                facts = self._flatten_dict(profile_data)
                for key, val in facts.items():
                    if val and not str(val).startswith("["):
                        category = key.split(".")[0]
                        cursor.execute(
                            """
                            INSERT INTO clinic_facts (key, value, category, updated_at)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                            """,
                            (key, str(val), category, now),
                        )

            # Sync FAQs
            if faqs_path.is_file():
                faqs_data = json.loads(faqs_path.read_text(encoding="utf-8")) or []
                for faq in faqs_data:
                    faq_id = faq.get("id")
                    if not faq_id:
                        continue
                    cat = faq.get("category", "general")
                    q_ar = (faq.get("question") or {}).get("ar", "")
                    ans_ar = (faq.get("answer") or {}).get("ar", "")
                    keywords = ",".join(faq.get("keywords", []))
                    approved = 1 if faq.get("approved_by_doctor") else 0
                    cursor.execute(
                        """
                        INSERT INTO faqs (id, category, question_ar, answer_ar, keywords, approved, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            category=excluded.category,
                            question_ar=excluded.question_ar,
                            answer_ar=excluded.answer_ar,
                            keywords=excluded.keywords,
                            approved=excluded.approved,
                            updated_at=excluded.updated_at
                        """,
                        (faq_id, cat, q_ar, ans_ar, keywords, approved, now),
                    )

            conn.commit()
        logger.info("Database synced successfully with knowledge files.")

    def get_fact(self, key: str) -> str | None:
        """Return a single clinic fact by its dotted key (e.g. 'working_hours.saturday')."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM clinic_facts WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else None

    def find_direct_faq(self, user_message: str) -> dict[str, str] | None:
        """Best matching approved FAQ for `user_message`, or None.

        Returns a mapping with the FAQ `id`, `category` and `answer` so callers
        can special-case categories (e.g. make working hours today-aware).
        """
        norm_query = normalize_arabic(user_message)
        words = set(norm_query.split())

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, category, answer_ar, keywords FROM faqs WHERE approved = 1"
            )
            rows = cursor.fetchall()

            best_match: dict[str, str] | None = None
            highest_score = 0

            for row in rows:
                raw_keywords = row["keywords"] or ""
                kw_list = [k.strip() for k in raw_keywords.split(",") if k.strip()]
                norm_kws = [normalize_arabic(k) for k in kw_list]

                # Check for direct keyword overlap
                matches = sum(1 for kw in norm_kws if kw in norm_query or kw in words)
                if matches > highest_score and matches >= 1:
                    highest_score = matches
                    best_match = {
                        "id": row["id"],
                        "category": row["category"],
                        "answer": row["answer_ar"],
                    }

            return best_match

    def save_message(self, user_id: str, role: str, content: str) -> None:
        """Persist a conversation turn in SQLite."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO conversation_messages (user_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, role, content, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()

    def get_recent_history(self, user_id: str, limit: int = 10) -> list[dict[str, str]]:
        """Retrieve recent turns for user in chronological order."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT role, content FROM conversation_messages
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            rows = cursor.fetchall()
            # Reverse to chronological
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    def clear_history(self, user_id: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM conversation_messages WHERE user_id = ?", (user_id,))
            conn.commit()

    @staticmethod
    def _flatten_dict(d: dict[str, Any], parent_key: str = "", sep: str = ".") -> dict[str, Any]:
        items: list[tuple[str, Any]] = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(AssistantDatabase._flatten_dict(v, new_key, sep=sep).items())
            else:
                items.append((new_key, v))
        return dict(items)
