"""Tests for the evaluator agent with mocked Claude."""

from unittest.mock import MagicMock, patch

import pytest

from jitter.agents.evaluator import EvaluatorAgent
from jitter.models import EvaluatorResult, IdeaEvaluation, ScoutResult, TrendingIdea


@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.anthropic_api_key = "fake-key"
    cfg.model_default = "claude-sonnet-4-6"
    return cfg


@pytest.fixture
def scout_result():
    return ScoutResult(
        ideas=[
            TrendingIdea(
                title="AI Code Reviewer",
                description="Reviews code with AI",
                source_url="https://example.com/1",
                category="ai",
                buzz_score=8,
            ),
            TrendingIdea(
                title="CLI Dashboard",
                description="Terminal dashboard for system stats",
                source_url="https://example.com/2",
                category="devtools",
                buzz_score=6,
            ),
        ],
        search_queries_used=["trending tools"],
    )


@pytest.fixture
def eval_result(scout_result):
    return EvaluatorResult(
        evaluations=[
            IdeaEvaluation(
                idea_title="AI Code Reviewer",
                feasibility_score=8,
                novelty_score=7,
                usefulness_score=9,
                overall_score=8,
                reasoning="Highly feasible and useful",
            ),
            IdeaEvaluation(
                idea_title="CLI Dashboard",
                feasibility_score=7,
                novelty_score=5,
                usefulness_score=6,
                overall_score=6,
                reasoning="Common concept, lower novelty",
            ),
        ],
        selected_idea=scout_result.ideas[0],
        selection_reasoning="Best overall score with high feasibility",
    )


@patch("jitter.agents.evaluator.AnthropicService")
def test_evaluator_selects_best_idea(
    mock_anthropic_cls, mock_config, scout_result, eval_result
):
    mock_anthropic = MagicMock()
    mock_anthropic.generate_structured.return_value = eval_result
    mock_anthropic_cls.return_value = mock_anthropic

    evaluator = EvaluatorAgent(mock_config)
    result = evaluator.evaluate(scout_result, past_project_names=[])

    assert isinstance(result, EvaluatorResult)
    assert result.selected_idea.title == "AI Code Reviewer"
    assert len(result.evaluations) == 2


@patch("jitter.agents.evaluator.AnthropicService")
def test_evaluator_includes_past_projects(
    mock_anthropic_cls, mock_config, scout_result, eval_result
):
    mock_anthropic = MagicMock()
    mock_anthropic.generate_structured.return_value = eval_result
    mock_anthropic_cls.return_value = mock_anthropic

    evaluator = EvaluatorAgent(mock_config)
    evaluator.evaluate(scout_result, past_project_names=["old_project", "another"])

    call_args = mock_anthropic.generate_structured.call_args
    user_msg = call_args.kwargs["user_message"]
    assert "old_project" in user_msg
    assert "another" in user_msg


@patch("jitter.agents.evaluator.AnthropicService")
def test_evaluator_passes_correct_output_model(
    mock_anthropic_cls, mock_config, scout_result, eval_result
):
    mock_anthropic = MagicMock()
    mock_anthropic.generate_structured.return_value = eval_result
    mock_anthropic_cls.return_value = mock_anthropic

    evaluator = EvaluatorAgent(mock_config)
    evaluator.evaluate(scout_result, past_project_names=[])

    call_args = mock_anthropic.generate_structured.call_args
    assert call_args.kwargs["output_model"] == EvaluatorResult


@patch("jitter.agents.evaluator.AnthropicService")
def test_evaluator_includes_category_cooldown(
    mock_anthropic_cls, mock_config, scout_result, eval_result
):
    mock_anthropic = MagicMock()
    mock_anthropic.generate_structured.return_value = eval_result
    mock_anthropic_cls.return_value = mock_anthropic

    evaluator = EvaluatorAgent(mock_config)
    evaluator.evaluate(
        scout_result,
        past_project_names=[],
        recent_categories={"ai": 2, "devtools": 1},
    )

    call_args = mock_anthropic.generate_structured.call_args
    user_msg = call_args.kwargs["user_message"]
    assert "Category cooldown" in user_msg
    assert '"ai": 2' in user_msg
