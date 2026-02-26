"""Integration test for the pipeline with all external services mocked."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from jitter.agents.dedup import DedupVerdict
from jitter.models import (
    EvaluatorResult,
    FileSpec,
    GeneratedFile,
    IdeaEvaluation,
    ImplementationPhase,
    PhaseCodeResult,
    PipelineStatus,
    PlannerResult,
    ProjectBlueprint,
    ProjectType,
    ReadmeResult,
    ScoutResult,
    TrendingIdea,
)
from jitter.pipeline import Pipeline


@pytest.fixture
def mock_config(tmp_path):
    cfg = MagicMock()
    cfg.anthropic_api_key = "fake-key"
    cfg.tavily_api_key = "fake-tavily-key"
    cfg.github_token = ""
    cfg.github_org = None
    cfg.github_private = False
    cfg.github_topic_tags = ["ai-generated"]
    cfg.model_default = "claude-sonnet-4-6"
    cfg.model_quality = "claude-opus-4-6"
    cfg.model_max_tokens = 8000
    cfg.scout_search_queries = ["trending tools"]
    cfg.scout_max_results_per_query = 3
    cfg.scout_topic = "news"
    cfg.scout_time_range = "week"
    cfg.pipeline_max_phases = 3
    cfg.pipeline_max_files_per_phase = 5
    cfg.pipeline_test_timeout_seconds = 30
    cfg.pipeline_max_retries_per_phase = 2
    cfg.logging_level = "WARNING"
    cfg.logging_file = None
    cfg.history_db_path = str(tmp_path / "test.db")
    cfg.output_dir = str(tmp_path / "output")
    return cfg


@pytest.fixture
def mock_idea():
    return TrendingIdea(
        title="Fast CLI Logger",
        description="A blazing-fast CLI logging utility.",
        source_url="https://example.com/fast-logger",
        category="devtools",
        buzz_score=9,
    )


@pytest.fixture
def mock_blueprint():
    return ProjectBlueprint(
        project_name="fast_cli_logger",
        project_type=ProjectType.CLI_TOOL,
        description="A blazing-fast CLI logging utility for developers.",
        tech_stack=["Python", "Click"],
        file_structure=[
            FileSpec(path="pyproject.toml", purpose="Project metadata"),
            FileSpec(path="logger/__init__.py", purpose="Package"),
            FileSpec(path="logger/main.py", purpose="Entry point"),
        ],
        dependencies=["click"],
        key_features=["Fast", "Colorful", "Configurable"],
    )


@pytest.fixture
def mock_plan():
    return PlannerResult(
        phases=[
            ImplementationPhase(
                phase_number=1,
                title="Setup",
                description="Project scaffold",
                files_to_create=["pyproject.toml", "logger/__init__.py"],
                commit_message="feat: initialize project",
            ),
            ImplementationPhase(
                phase_number=2,
                title="Core",
                description="Main logic",
                files_to_create=["logger/main.py"],
                depends_on_phases=[1],
                commit_message="feat: add core logging logic",
            ),
        ],
        estimated_total_files=3,
        testing_strategy="pytest",
    )


@pytest.fixture
def mock_phase_results():
    return [
        PhaseCodeResult(
            phase_number=1,
            files=[
                GeneratedFile(
                    path="pyproject.toml",
                    content='[project]\nname = "fast-cli-logger"\n',
                    language="toml",
                ),
                GeneratedFile(
                    path="logger/__init__.py",
                    content='"""Fast CLI Logger."""\n',
                    language="python",
                ),
            ],
        ),
        PhaseCodeResult(
            phase_number=2,
            files=[
                GeneratedFile(
                    path="logger/main.py",
                    content='"""Main entry point."""\n\ndef main():\n    print("hello")\n',
                    language="python",
                ),
            ],
        ),
    ]


@patch("jitter.pipeline.ScoutAgent")
@patch("jitter.pipeline.EvaluatorAgent")
@patch("jitter.pipeline.DedupAgent")
@patch("jitter.pipeline.ArchitectAgent")
@patch("jitter.pipeline.PlannerAgent")
@patch("jitter.pipeline.CoderAgent")
@patch("jitter.pipeline.DocumenterAgent")
@patch("jitter.pipeline.TestRunner")
def test_pipeline_dry_run(
    mock_test_runner_cls,
    mock_documenter_cls,
    mock_coder_cls,
    mock_planner_cls,
    mock_architect_cls,
    mock_dedup_cls,
    mock_evaluator_cls,
    mock_scout_cls,
    mock_config,
    mock_idea,
    mock_blueprint,
    mock_plan,
    mock_phase_results,
):
    # Setup scout mock
    scout_result = ScoutResult(
        ideas=[mock_idea],
        search_queries_used=["trending tools"],
    )
    mock_scout = MagicMock()
    mock_scout.search.return_value = scout_result
    mock_scout_cls.return_value = mock_scout

    # Setup evaluator mock
    eval_result = EvaluatorResult(
        evaluations=[
            IdeaEvaluation(
                idea_title=mock_idea.title,
                feasibility_score=9,
                novelty_score=7,
                usefulness_score=8,
                overall_score=8,
                reasoning="Great idea",
            )
        ],
        selected_idea=mock_idea,
        selection_reasoning="Best overall",
    )
    mock_evaluator = MagicMock()
    mock_evaluator.evaluate.return_value = eval_result
    mock_evaluator_cls.return_value = mock_evaluator

    # Setup dedup mock - idea is NOT a duplicate
    mock_dedup = MagicMock()
    mock_dedup.check.return_value = DedupVerdict(
        is_duplicate=False,
        similar_to=None,
        reasoning="Unique idea",
    )
    mock_dedup_cls.return_value = mock_dedup

    # Setup architect mock
    mock_architect = MagicMock()
    mock_architect.design.return_value = mock_blueprint
    mock_architect_cls.return_value = mock_architect

    # Setup planner mock
    mock_planner = MagicMock()
    mock_planner.plan.return_value = mock_plan
    mock_planner_cls.return_value = mock_planner

    # Setup coder mock - returns phase results sequentially
    mock_coder = MagicMock()
    mock_coder.generate.side_effect = mock_phase_results
    mock_coder_cls.return_value = mock_coder

    # Setup documenter mock
    mock_documenter = MagicMock()
    mock_documenter.generate.return_value = ReadmeResult(
        content="# Fast CLI Logger\n\nA logging tool."
    )
    mock_documenter_cls.return_value = mock_documenter

    # Setup test runner mock
    mock_runner = MagicMock()
    mock_runner.run_tests.return_value = (True, "All tests passed")
    mock_test_runner_cls.return_value = mock_runner

    # Run pipeline in dry-run mode
    pipeline = Pipeline(mock_config, dry_run=True)
    result = pipeline.run()

    # Verify pipeline completed
    assert result.status == PipelineStatus.COMPLETED
    assert result.selected_idea.title == "Fast CLI Logger"
    assert result.blueprint.project_name == "fast_cli_logger"
    assert result.github_url is None  # dry run

    # Verify all agents were called
    mock_scout.search.assert_called_once()
    mock_evaluator.evaluate.assert_called_once()
    mock_dedup.check.assert_called_once()
    mock_architect.design.assert_called_once()
    mock_planner.plan.assert_called_once()
    assert mock_coder.generate.call_count == 2  # 2 phases
    mock_documenter.generate.assert_called_once()

    # Verify files were saved locally
    from pathlib import Path

    output_dir = Path(mock_config.output_dir) / "fast_cli_logger"
    assert output_dir.exists()
    assert (output_dir / "README.md").exists()
    assert (output_dir / "pyproject.toml").exists()
    assert (output_dir / "logger" / "main.py").exists()


@patch("jitter.pipeline.ScoutAgent")
@patch("jitter.pipeline.TestRunner")
def test_pipeline_handles_failure(
    mock_test_runner_cls,
    mock_scout_cls,
    mock_config,
):
    # Scout fails
    mock_scout = MagicMock()
    mock_scout.search.side_effect = RuntimeError("Search API down")
    mock_scout_cls.return_value = mock_scout

    mock_runner = MagicMock()
    mock_test_runner_cls.return_value = mock_runner

    pipeline = Pipeline(mock_config, dry_run=True)

    with pytest.raises(RuntimeError, match="Search API down"):
        pipeline.run()

    # Verify failure was recorded in history
    from jitter.store.history import HistoryStore

    store = HistoryStore(mock_config.history_db_path)
    runs = store.get_recent_runs()
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert "Search API down" in runs[0]["error"]


@patch("jitter.pipeline.ScoutAgent")
@patch("jitter.pipeline.EvaluatorAgent")
@patch("jitter.pipeline.DedupAgent")
@patch("jitter.pipeline.ArchitectAgent")
@patch("jitter.pipeline.PlannerAgent")
@patch("jitter.pipeline.CoderAgent")
@patch("jitter.pipeline.DocumenterAgent")
@patch("jitter.pipeline.TestRunner")
def test_pipeline_dedup_retry_selects_alternative(
    mock_test_runner_cls,
    mock_documenter_cls,
    mock_coder_cls,
    mock_planner_cls,
    mock_architect_cls,
    mock_dedup_cls,
    mock_evaluator_cls,
    mock_scout_cls,
    mock_config,
    mock_blueprint,
    mock_plan,
    mock_phase_results,
):
    """When the first pick is flagged as a duplicate, pipeline retries with the next-best idea."""
    idea_a = TrendingIdea(
        title="AI Code Reviewer",
        description="Reviews code with AI",
        source_url="https://example.com/1",
        category="ai",
        buzz_score=8,
    )
    idea_b = TrendingIdea(
        title="Fast CLI Logger",
        description="A blazing-fast CLI logging utility.",
        source_url="https://example.com/2",
        category="devtools",
        buzz_score=7,
    )

    # Scout returns both ideas
    scout_result = ScoutResult(
        ideas=[idea_a, idea_b],
        search_queries_used=["trending tools"],
    )
    mock_scout = MagicMock()
    mock_scout.search.return_value = scout_result
    mock_scout_cls.return_value = mock_scout

    # Evaluator selects idea_a (highest score), but also evaluates idea_b
    eval_result = EvaluatorResult(
        evaluations=[
            IdeaEvaluation(
                idea_title="AI Code Reviewer",
                feasibility_score=9,
                novelty_score=7,
                usefulness_score=8,
                overall_score=8,
                reasoning="Great idea",
            ),
            IdeaEvaluation(
                idea_title="Fast CLI Logger",
                feasibility_score=8,
                novelty_score=6,
                usefulness_score=7,
                overall_score=7,
                reasoning="Good but less novel",
            ),
        ],
        selected_idea=idea_a,
        selection_reasoning="Best overall score",
    )
    mock_evaluator = MagicMock()
    mock_evaluator.evaluate.return_value = eval_result
    mock_evaluator_cls.return_value = mock_evaluator

    # Dedup: first call flags as duplicate, second call accepts
    mock_dedup = MagicMock()
    mock_dedup.check.side_effect = [
        DedupVerdict(
            is_duplicate=True,
            similar_to="AI Code Review Bot",
            reasoning="Same concept as past project",
        ),
        DedupVerdict(
            is_duplicate=False,
            similar_to=None,
            reasoning="Unique idea",
        ),
    ]
    mock_dedup_cls.return_value = mock_dedup

    # Remaining agents
    mock_architect = MagicMock()
    mock_architect.design.return_value = mock_blueprint
    mock_architect_cls.return_value = mock_architect

    mock_planner = MagicMock()
    mock_planner.plan.return_value = mock_plan
    mock_planner_cls.return_value = mock_planner

    mock_coder = MagicMock()
    mock_coder.generate.side_effect = mock_phase_results
    mock_coder_cls.return_value = mock_coder

    mock_documenter = MagicMock()
    mock_documenter.generate.return_value = ReadmeResult(
        content="# Fast CLI Logger\n\nA logging tool."
    )
    mock_documenter_cls.return_value = mock_documenter

    mock_runner = MagicMock()
    mock_runner.run_tests.return_value = (True, "All tests passed")
    mock_test_runner_cls.return_value = mock_runner

    pipeline = Pipeline(mock_config, dry_run=True)
    result = pipeline.run()

    assert result.status == PipelineStatus.COMPLETED
    # The selected idea should be idea_b since idea_a was flagged as duplicate
    assert result.selected_idea.title == "Fast CLI Logger"
    # Dedup was called twice (first for idea_a, then for idea_b)
    assert mock_dedup.check.call_count == 2
