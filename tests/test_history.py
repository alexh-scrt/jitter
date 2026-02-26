"""Tests for the SQLite history store."""

import pytest

from jitter.models import PipelineRun, PipelineStatus
from jitter.store.history import HistoryStore


@pytest.fixture
def store(tmp_path):
    db_path = str(tmp_path / "test_history.db")
    return HistoryStore(db_path)


def test_init_creates_tables(store):
    """DB should be created and usable immediately."""
    runs = store.get_recent_runs()
    assert runs == []


def test_record_and_get_run(store, sample_run):
    store.record_run_start(sample_run)
    runs = store.get_recent_runs()
    assert len(runs) == 1
    assert runs[0]["run_id"] == "test123"
    assert runs[0]["status"] == "running"


def test_record_run_complete(store, sample_run):
    store.record_run_start(sample_run)
    store.record_run_complete("test123", "https://github.com/user/project")
    runs = store.get_recent_runs()
    assert runs[0]["status"] == "completed"
    assert runs[0]["github_url"] == "https://github.com/user/project"


def test_record_run_failed(store, sample_run):
    store.record_run_start(sample_run)
    store.record_run_failed("test123", "Something broke")
    runs = store.get_recent_runs()
    assert runs[0]["status"] == "failed"
    assert runs[0]["error"] == "Something broke"


def test_record_built_project(store, sample_run, sample_blueprint, sample_idea):
    store.record_run_start(sample_run)
    store.record_built_project(
        "test123", sample_blueprint, sample_idea, "https://github.com/user/proj"
    )
    names = store.get_past_project_names()
    assert "ai_code_reviewer" in names

    titles = store.get_past_idea_titles()
    assert "AI Code Reviewer" in titles


def test_get_all_projects(store, sample_run, sample_blueprint, sample_idea):
    store.record_run_start(sample_run)
    store.record_built_project("test123", sample_blueprint, sample_idea)
    projects = store.get_all_projects()
    assert len(projects) == 1
    assert projects[0]["project_name"] == "ai_code_reviewer"


def test_update_run_idea(store, sample_run, sample_idea):
    store.record_run_start(sample_run)
    store.update_run_idea("test123", sample_idea)
    # No assertion on content, just verify it doesn't error


def test_update_run_blueprint(store, sample_run, sample_blueprint):
    store.record_run_start(sample_run)
    store.update_run_blueprint("test123", sample_blueprint)


def test_recent_runs_limit(store):
    from datetime import datetime

    for i in range(5):
        run = PipelineRun(
            run_id=f"run{i}",
            started_at=datetime(2026, 2, 25, i, 0, 0),
        )
        store.record_run_start(run)

    runs = store.get_recent_runs(limit=3)
    assert len(runs) == 3


def test_past_project_names_empty(store):
    assert store.get_past_project_names() == []


def test_past_idea_titles_empty(store):
    assert store.get_past_idea_titles() == []
