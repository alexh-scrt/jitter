"""Tests for all three dedup layers."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from jitter.agents.dedup import DedupAgent, DedupVerdict
from jitter.models import PipelineRun, ProjectBlueprint, ProjectType, TrendingIdea, FileSpec
from jitter.store.history import HistoryStore


# ---- Layer 1: Fuzzy matching tests ----


@pytest.fixture
def store_with_projects(tmp_path):
    """History store pre-populated with a few past projects."""
    store = HistoryStore(str(tmp_path / "test.db"))
    run = PipelineRun(run_id="r1", started_at=datetime.now())
    store.record_run_start(run)

    projects = [
        ("markdown_previewer", "Markdown CLI Previewer", "devtools", "A CLI tool to preview markdown files in the terminal."),
        ("ai_code_reviewer", "AI Code Review Bot", "ai", "A bot that reviews pull requests using AI and suggests improvements."),
        ("json_formatter", "JSON Formatter CLI", "devtools", "A fast CLI tool to format and validate JSON files."),
    ]
    for name, title, category, desc in projects:
        bp = ProjectBlueprint(
            project_name=name,
            project_type=ProjectType.CLI_TOOL,
            description=desc,
            tech_stack=["Python"],
            file_structure=[FileSpec(path="main.py", purpose="Entry")],
            dependencies=[],
            key_features=["Feature"],
        )
        idea = TrendingIdea(
            title=title,
            description=desc,
            source_url="https://example.com",
            category=category,
            buzz_score=7,
        )
        store.record_built_project("r1", bp, idea)
    return store


def test_fuzzy_exact_title_match(store_with_projects):
    is_dup, match = store_with_projects.is_fuzzy_duplicate("AI Code Review Bot")
    assert is_dup
    assert match == "AI Code Review Bot"


def test_fuzzy_similar_title(store_with_projects):
    # "Markdown Terminal Previewer" should match "Markdown CLI Previewer"
    is_dup, match = store_with_projects.is_fuzzy_duplicate("Markdown Terminal Previewer")
    assert is_dup


def test_fuzzy_different_idea(store_with_projects):
    is_dup, match = store_with_projects.is_fuzzy_duplicate("Real-time Stock Price Tracker")
    assert not is_dup
    assert match is None


def test_fuzzy_similar_project_name(store_with_projects):
    # "json formatter" should match project_name "json_formatter"
    is_dup, match = store_with_projects.is_fuzzy_duplicate("JSON Formatter")
    assert is_dup


def test_fuzzy_empty_history(tmp_path):
    store = HistoryStore(str(tmp_path / "empty.db"))
    is_dup, match = store.is_fuzzy_duplicate("Any Idea At All")
    assert not is_dup


def test_tokenize():
    tokens = HistoryStore._tokenize("AI Code Review Bot for Python")
    assert "ai" in tokens
    assert "code" in tokens
    assert "review" in tokens
    assert "bot" in tokens
    assert "python" in tokens
    # "for" is a stopword, should be removed
    assert "for" not in tokens


def test_tokenize_snake_case():
    tokens = HistoryStore._tokenize("json_formatter_cli")
    assert "json" in tokens
    assert "formatter" in tokens
    assert "cli" in tokens


def test_jaccard_identical():
    assert HistoryStore._jaccard({"a", "b", "c"}, {"a", "b", "c"}) == 1.0


def test_jaccard_disjoint():
    assert HistoryStore._jaccard({"a", "b"}, {"c", "d"}) == 0.0


def test_jaccard_partial():
    sim = HistoryStore._jaccard({"a", "b", "c"}, {"b", "c", "d"})
    assert 0.4 < sim < 0.6  # 2/4 = 0.5


def test_jaccard_empty():
    assert HistoryStore._jaccard(set(), {"a"}) == 0.0


# ---- Layer 4: Category cooldown tests ----


def test_recent_categories_with_data(store_with_projects):
    # All projects were just created, so all should be "recent"
    cats = store_with_projects.get_recent_categories(days=3)
    assert cats["devtools"] == 2
    assert cats["ai"] == 1


def test_recent_categories_empty(tmp_path):
    store = HistoryStore(str(tmp_path / "empty.db"))
    cats = store.get_recent_categories(days=3)
    assert cats == {}


def test_past_projects_summary(store_with_projects):
    summary = store_with_projects.get_past_projects_summary()
    assert len(summary) == 3
    assert all("idea_title" in p for p in summary)
    assert all("description" in p for p in summary)
    assert all("idea_category" in p for p in summary)


# ---- Layer 3: Claude dedup judge tests ----


@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.anthropic_api_key = "fake"
    cfg.model_default = "claude-sonnet-4-6"
    return cfg


@patch("jitter.agents.dedup.AnthropicService")
def test_dedup_agent_no_past_projects(mock_cls, mock_config):
    """With no past projects, should always return not-duplicate."""
    agent = DedupAgent(mock_config)
    idea = TrendingIdea(
        title="New Idea",
        description="Something new",
        source_url="https://x.com",
        category="ai",
        buzz_score=8,
    )
    verdict = agent.check(idea, past_projects=[])
    assert not verdict.is_duplicate
    # Claude should NOT be called when there are no past projects
    mock_cls.return_value.generate_structured.assert_not_called()


@patch("jitter.agents.dedup.AnthropicService")
def test_dedup_agent_detects_duplicate(mock_cls, mock_config):
    mock_svc = MagicMock()
    mock_svc.generate_structured.return_value = DedupVerdict(
        is_duplicate=True,
        similar_to="AI Code Review Bot",
        reasoning="Same concept",
    )
    mock_cls.return_value = mock_svc

    agent = DedupAgent(mock_config)
    idea = TrendingIdea(
        title="AI PR Reviewer",
        description="Reviews PRs with AI",
        source_url="https://x.com",
        category="ai",
        buzz_score=7,
    )
    past = [{"idea_title": "AI Code Review Bot", "description": "Reviews code", "idea_category": "ai"}]
    verdict = agent.check(idea, past)
    assert verdict.is_duplicate
    assert verdict.similar_to == "AI Code Review Bot"


@patch("jitter.agents.dedup.AnthropicService")
def test_dedup_agent_accepts_unique(mock_cls, mock_config):
    mock_svc = MagicMock()
    mock_svc.generate_structured.return_value = DedupVerdict(
        is_duplicate=False,
        similar_to=None,
        reasoning="Completely different domain",
    )
    mock_cls.return_value = mock_svc

    agent = DedupAgent(mock_config)
    idea = TrendingIdea(
        title="Weather Dashboard",
        description="Live weather display",
        source_url="https://x.com",
        category="web",
        buzz_score=6,
    )
    past = [{"idea_title": "AI Code Review Bot", "description": "Reviews code", "idea_category": "ai"}]
    verdict = agent.check(idea, past)
    assert not verdict.is_duplicate
