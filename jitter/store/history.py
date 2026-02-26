"""SQLite-backed project history for tracking past runs and avoiding duplicates."""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta

from jitter.models import (
    PipelineRun,
    PipelineStatus,
    ProjectBlueprint,
    TrendingIdea,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    selected_idea_json TEXT,
    blueprint_json TEXT,
    github_url TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS built_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    idea_title TEXT NOT NULL,
    idea_category TEXT NOT NULL,
    description TEXT NOT NULL,
    github_url TEXT,
    built_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_project_name ON built_projects(project_name);
CREATE INDEX IF NOT EXISTS idx_idea_title ON built_projects(idea_title);
"""


class HistoryStore:
    """Tracks pipeline runs and built projects in SQLite."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record_run_start(self, run: PipelineRun) -> None:
        """Record the start of a pipeline run."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO pipeline_runs (run_id, started_at, status) VALUES (?, ?, ?)",
                (run.run_id, run.started_at.isoformat(), run.status.value),
            )

    def update_run_idea(self, run_id: str, idea: TrendingIdea) -> None:
        """Update the selected idea for a run."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE pipeline_runs SET selected_idea_json = ? WHERE run_id = ?",
                (idea.model_dump_json(), run_id),
            )

    def update_run_blueprint(
        self, run_id: str, blueprint: ProjectBlueprint
    ) -> None:
        """Update the blueprint for a run."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE pipeline_runs SET blueprint_json = ? WHERE run_id = ?",
                (blueprint.model_dump_json(), run_id),
            )

    def record_run_complete(self, run_id: str, github_url: str) -> None:
        """Mark a run as completed."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE pipeline_runs SET status = ?, completed_at = ?, github_url = ? WHERE run_id = ?",
                (
                    PipelineStatus.COMPLETED.value,
                    datetime.now().isoformat(),
                    github_url,
                    run_id,
                ),
            )

    def record_run_failed(self, run_id: str, error: str) -> None:
        """Mark a run as failed."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE pipeline_runs SET status = ?, completed_at = ?, error = ? WHERE run_id = ?",
                (
                    PipelineStatus.FAILED.value,
                    datetime.now().isoformat(),
                    error,
                    run_id,
                ),
            )

    def record_built_project(
        self,
        run_id: str,
        blueprint: ProjectBlueprint,
        idea: TrendingIdea,
        github_url: str | None = None,
    ) -> None:
        """Record a successfully built project."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO built_projects
                   (run_id, project_name, idea_title, idea_category, description, github_url, built_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    run_id,
                    blueprint.project_name,
                    idea.title,
                    idea.category,
                    blueprint.description,
                    github_url,
                    datetime.now().isoformat(),
                ),
            )

    def get_past_project_names(self) -> list[str]:
        """Get all previously built project names (for dedup)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT project_name FROM built_projects"
            ).fetchall()
            return [row["project_name"] for row in rows]

    def get_past_idea_titles(self) -> list[str]:
        """Get all previously built idea titles (for dedup)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT idea_title FROM built_projects"
            ).fetchall()
            return [row["idea_title"] for row in rows]

    def get_recent_runs(self, limit: int = 10) -> list[dict]:
        """Get recent pipeline runs with optional project info."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT r.run_id, r.started_at, r.completed_at, r.status,
                          r.github_url, r.error, p.project_name
                   FROM pipeline_runs r
                   LEFT JOIN built_projects p ON r.run_id = p.run_id
                   ORDER BY r.started_at DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_all_projects(self) -> list[dict]:
        """Get all built projects."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT project_name, idea_title, idea_category,
                          description, github_url, built_at
                   FROM built_projects
                   ORDER BY built_at DESC"""
            ).fetchall()
            return [dict(row) for row in rows]

    # --- Dedup: Layer 1 - Fuzzy title matching ---

    def is_fuzzy_duplicate(self, title: str, threshold: float = 0.55) -> tuple[bool, str | None]:
        """Check if a title is too similar to any past project.

        Uses token-level Jaccard similarity (intersection / union of words).
        Returns (is_duplicate, matching_title_or_None).
        """
        title_tokens = self._tokenize(title)
        if not title_tokens:
            return False, None

        past_titles = self.get_past_idea_titles()
        past_names = self.get_past_project_names()
        past_descriptions = self._get_past_descriptions()

        # Check against titles, project names, and descriptions
        for past_title in past_titles:
            sim = self._jaccard(title_tokens, self._tokenize(past_title))
            if sim >= threshold:
                return True, past_title

        for past_name in past_names:
            # Convert snake_case/kebab-case project names to tokens
            sim = self._jaccard(title_tokens, self._tokenize(past_name))
            if sim >= threshold:
                return True, past_name

        # Check descriptions with a higher threshold (descriptions are longer)
        for desc in past_descriptions:
            sim = self._jaccard(title_tokens, self._tokenize(desc))
            if sim >= 0.4:
                return True, desc[:60]

        return False, None

    def _get_past_descriptions(self) -> list[str]:
        """Get all past project descriptions."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT description FROM built_projects"
            ).fetchall()
            return [row["description"] for row in rows]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Normalize and split text into a set of lowercase tokens.

        Strips common filler words and splits on non-alphanumeric chars.
        """
        stopwords = {
            "a", "an", "the", "for", "and", "or", "to", "of", "in", "on",
            "is", "it", "that", "this", "with", "as", "by", "from", "your",
            "using", "based", "tool", "app", "application", "simple", "new",
        }
        tokens = set(re.split(r"[^a-z0-9]+", text.lower()))
        tokens -= stopwords
        tokens.discard("")
        return tokens

    @staticmethod
    def _jaccard(a: set[str], b: set[str]) -> float:
        """Jaccard similarity between two token sets."""
        if not a or not b:
            return 0.0
        intersection = len(a & b)
        union = len(a | b)
        return intersection / union if union > 0 else 0.0

    # --- Dedup: Layer 4 - Category cooldown ---

    def get_recent_categories(self, days: int = 3) -> dict[str, int]:
        """Get category counts for projects built in the last N days.

        Returns {category: count} for the cooldown window.
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT idea_category FROM built_projects WHERE built_at >= ?",
                (cutoff,),
            ).fetchall()
            return dict(Counter(row["idea_category"] for row in rows))

    def get_past_projects_summary(self) -> list[dict]:
        """Get title + description for all past projects (for Claude dedup judge)."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT idea_title, description, idea_category FROM built_projects"
            ).fetchall()
            return [dict(row) for row in rows]
