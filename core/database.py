import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class DatabaseManager:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".directory_organizer" / "organizer.db"
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self.get_connection() as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS run_history (
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    summary TEXT,
                    changes_applied INTEGER DEFAULT 0,
                    changes_skipped INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS suggestions (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    original_path TEXT NOT NULL,
                    original_name TEXT NOT NULL,
                    proposed_name TEXT NOT NULL,
                    proposed_path TEXT NOT NULL,
                    action TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    rationale TEXT,
                    risk TEXT DEFAULT 'low',
                    apply INTEGER DEFAULT 1,
                    category TEXT,
                    FOREIGN KEY (run_id) REFERENCES run_history (id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS undo_log (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    operations TEXT NOT NULL,
                    applied INTEGER DEFAULT 0,
                    FOREIGN KEY (run_id) REFERENCES run_history (id) ON DELETE CASCADE
                )
                """
            )
            conn.commit()

    def start_run(self, run_id: str, started_at: str) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO run_history (id, started_at) VALUES (?, ?)",
                (run_id, started_at),
            )
            conn.commit()

    def finish_run(self, run_id: str, finished_at: str, summary: Dict, changes_applied: int, changes_skipped: int) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                UPDATE run_history
                SET finished_at = ?, summary = ?, changes_applied = ?, changes_skipped = ?
                WHERE id = ?
                """,
                (finished_at, json.dumps(summary), changes_applied, changes_skipped, run_id),
            )
            conn.commit()

    def add_suggestions(self, run_id: str, suggestions_list: List[Dict]) -> None:
        with self.get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO suggestions (
                    id, run_id, original_path, original_name, proposed_name, proposed_path, action, confidence, rationale, risk, apply, category
                ) VALUES (
                    :id, :run_id, :original_path, :original_name, :proposed_name, :proposed_path, :action, :confidence, :rationale, :risk, :apply, :category
                )
                """,
                [
                    {
                        "id": s["id"],
                        "run_id": run_id,
                        "original_path": s["original_path"],
                        "original_name": s["original_name"],
                        "proposed_name": s["proposed_name"],
                        "proposed_path": s["proposed_path"],
                        "action": s["action"],
                        "confidence": s.get("confidence", 1.0),
                        "rationale": s.get("rationale", ""),
                        "risk": s.get("risk", "low"),
                        "apply": 1 if s.get("apply", True) else 0,
                        "category": s.get("category", "Other"),
                    }
                    for s in suggestions_list
                ],
            )
            conn.commit()

    def update_suggestion(self, suggestion_id: str, apply: bool, proposed_name: Optional[str] = None, proposed_path: Optional[str] = None) -> None:
        with self.get_connection() as conn:
            if proposed_name is not None and proposed_path is not None:
                conn.execute(
                    """
                    UPDATE suggestions
                    SET apply = ?, proposed_name = ?, proposed_path = ?
                    WHERE id = ?
                    """,
                    (1 if apply else 0, proposed_name, proposed_path, suggestion_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE suggestions
                    SET apply = ?
                    WHERE id = ?
                    """,
                    (1 if apply else 0, suggestion_id),
                )
            conn.commit()

    def add_undo_log(self, undo_id: str, run_id: str, operations: List[Dict]) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "INSERT INTO undo_log (id, run_id, operations, applied) VALUES (?, ?, ?, 0)",
                (undo_id, run_id, json.dumps(operations)),
            )
            conn.commit()

    def mark_undo_applied(self, run_id: str) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE undo_log SET applied = 1 WHERE run_id = ?",
                (run_id,),
            )
            conn.commit()

    def get_suggestions(self, run_id: str) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM suggestions WHERE run_id = ?",
                (run_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_run_history(self) -> List[Dict]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM run_history ORDER BY started_at DESC"
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_last_run(self) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM run_history ORDER BY started_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_undo_log(self, run_id: str) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM undo_log WHERE run_id = ? AND applied = 0",
                (run_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_last_undo_log(self) -> Optional[Dict]:
        with self.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT u.* FROM undo_log u
                JOIN run_history r ON u.run_id = r.id
                WHERE u.applied = 0
                ORDER BY r.started_at DESC LIMIT 1
                """
            )
            row = cursor.fetchone()
            return dict(row) if row else None
