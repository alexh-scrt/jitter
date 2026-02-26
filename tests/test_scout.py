"""Tests for the scout agent with mocked external services."""

from unittest.mock import MagicMock, patch

import pytest

from jitter.agents.scout import ScoutAgent
from jitter.models import ScoutResult, TrendingIdea


@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.anthropic_api_key = "fake-key"
    cfg.tavily_api_key = "fake-tavily-key"
    cfg.model_default = "claude-sonnet-4-6"
    cfg.scout_search_queries = ["trending ai tools", "new dev tools"]
    cfg.scout_max_results_per_query = 3
    cfg.scout_topic = "news"
    cfg.scout_time_range = "week"
    return cfg


@pytest.fixture
def mock_tavily_response():
    return {
        "results": [
            {
                "title": "New AI Code Review Tool Goes Viral",
                "url": "https://example.com/article1",
                "content": "A new tool for reviewing code with AI has gained popularity.",
            },
            {
                "title": "Developer CLI Tools Trending This Week",
                "url": "https://example.com/article2",
                "content": "Several CLI tools are trending among developers.",
            },
        ]
    }


@pytest.fixture
def mock_scout_result():
    return ScoutResult(
        ideas=[
            TrendingIdea(
                title="AI Code Reviewer",
                description="CLI tool that reviews code using AI.",
                source_url="https://example.com/article1",
                category="ai",
                buzz_score=8,
            ),
            TrendingIdea(
                title="Dev CLI Toolkit",
                description="Collection of useful CLI utilities for developers.",
                source_url="https://example.com/article2",
                category="devtools",
                buzz_score=6,
            ),
        ],
        search_queries_used=["trending ai tools"],
    )


@patch("jitter.agents.scout.TavilyService")
@patch("jitter.agents.scout.AnthropicService")
def test_scout_search(
    mock_anthropic_cls, mock_tavily_cls, mock_config, mock_tavily_response, mock_scout_result
):
    # Setup mocks
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = mock_tavily_response
    mock_tavily_cls.return_value = mock_tavily

    mock_anthropic = MagicMock()
    mock_anthropic.generate_structured.return_value = mock_scout_result
    mock_anthropic_cls.return_value = mock_anthropic

    # Run scout
    scout = ScoutAgent(mock_config)
    result = scout.search()

    assert isinstance(result, ScoutResult)
    assert len(result.ideas) == 2
    assert result.ideas[0].title == "AI Code Reviewer"

    # Verify Tavily was called
    assert mock_tavily.search.call_count >= 1

    # Verify Anthropic was called with the raw results
    mock_anthropic.generate_structured.assert_called_once()
    call_kwargs = mock_anthropic.generate_structured.call_args
    assert call_kwargs.kwargs["output_model"] == ScoutResult


@patch("jitter.agents.scout.TavilyService")
@patch("jitter.agents.scout.AnthropicService")
def test_scout_deduplicates_urls(
    mock_anthropic_cls, mock_tavily_cls, mock_config, mock_scout_result
):
    # Return duplicate URLs across searches
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = {
        "results": [
            {"title": "Same Article", "url": "https://example.com/same", "content": "text"},
            {"title": "Same Article Again", "url": "https://example.com/same", "content": "text"},
        ]
    }
    mock_tavily_cls.return_value = mock_tavily

    mock_anthropic = MagicMock()
    mock_anthropic.generate_structured.return_value = mock_scout_result
    mock_anthropic_cls.return_value = mock_anthropic

    scout = ScoutAgent(mock_config)
    scout.search()

    # Check that the user message to Claude has deduplicated results
    call_args = mock_anthropic.generate_structured.call_args
    user_msg = call_args.kwargs["user_message"]
    # Only one instance of the URL should appear
    assert user_msg.count("https://example.com/same") == 1


@patch("jitter.agents.scout.TavilyService")
@patch("jitter.agents.scout.AnthropicService")
def test_scout_with_past_ideas(
    mock_anthropic_cls, mock_tavily_cls, mock_config, mock_tavily_response, mock_scout_result
):
    mock_tavily = MagicMock()
    mock_tavily.search.return_value = mock_tavily_response
    mock_tavily_cls.return_value = mock_tavily

    mock_anthropic = MagicMock()
    mock_anthropic.generate_structured.return_value = mock_scout_result
    mock_anthropic_cls.return_value = mock_anthropic

    scout = ScoutAgent(mock_config)
    scout.search(past_idea_titles=["Old Project"])

    # Verify past ideas are included in the prompt
    call_args = mock_anthropic.generate_structured.call_args
    user_msg = call_args.kwargs["user_message"]
    assert "Old Project" in user_msg


@patch("jitter.agents.scout.TavilyService")
@patch("jitter.agents.scout.AnthropicService")
def test_scout_handles_tavily_failure(mock_anthropic_cls, mock_tavily_cls, mock_config):
    mock_tavily = MagicMock()
    mock_tavily.search.side_effect = Exception("API Error")
    mock_tavily_cls.return_value = mock_tavily

    mock_anthropic = MagicMock()
    mock_anthropic_cls.return_value = mock_anthropic

    scout = ScoutAgent(mock_config)

    with pytest.raises(RuntimeError, match="All Tavily searches failed"):
        scout.search()
