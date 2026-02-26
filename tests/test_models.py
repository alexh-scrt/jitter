"""Tests for Pydantic data models."""

from datetime import datetime

from jitter.models import (
    EvaluatorResult,
    FileSpec,
    GeneratedFile,
    IdeaEvaluation,
    ImplementationPhase,
    PhaseCodeResult,
    PipelineRun,
    PipelineStatus,
    PlannerResult,
    ProjectBlueprint,
    ProjectType,
    ReadmeResult,
    ScoutResult,
    TrendingIdea,
)


def _make_idea(**overrides):
    defaults = {
        "title": "AI Code Reviewer",
        "description": "A CLI tool that reviews code using AI.",
        "source_url": "https://example.com/article",
        "category": "ai",
        "buzz_score": 8,
    }
    defaults.update(overrides)
    return TrendingIdea(**defaults)


def test_trending_idea_creation():
    idea = _make_idea()
    assert idea.title == "AI Code Reviewer"
    assert idea.buzz_score == 8


def test_trending_idea_serialization_roundtrip():
    idea = _make_idea()
    json_str = idea.model_dump_json()
    restored = TrendingIdea.model_validate_json(json_str)
    assert restored == idea


def test_scout_result():
    result = ScoutResult(
        ideas=[_make_idea(), _make_idea(title="Second Idea")],
        search_queries_used=["trending ai tools"],
    )
    assert len(result.ideas) == 2
    data = result.model_dump()
    assert len(data["ideas"]) == 2


def test_idea_evaluation():
    ev = IdeaEvaluation(
        idea_title="Test",
        feasibility_score=7,
        novelty_score=8,
        usefulness_score=6,
        overall_score=7,
        reasoning="Good idea",
    )
    assert ev.overall_score == 7


def test_evaluator_result():
    idea = _make_idea()
    result = EvaluatorResult(
        evaluations=[
            IdeaEvaluation(
                idea_title=idea.title,
                feasibility_score=7,
                novelty_score=8,
                usefulness_score=6,
                overall_score=7,
                reasoning="Good",
            )
        ],
        selected_idea=idea,
        selection_reasoning="Best overall",
    )
    assert result.selected_idea.title == "AI Code Reviewer"


def test_project_blueprint():
    bp = ProjectBlueprint(
        project_name="code_reviewer",
        project_type=ProjectType.CLI_TOOL,
        description="A CLI code review tool.",
        tech_stack=["Python", "Click"],
        file_structure=[
            FileSpec(path="main.py", purpose="Entry point"),
            FileSpec(path="reviewer.py", purpose="Review logic"),
        ],
        dependencies=["click", "rich"],
        key_features=["Fast reviews", "Multiple languages"],
    )
    assert bp.project_type == ProjectType.CLI_TOOL
    assert len(bp.file_structure) == 2


def test_project_blueprint_serialization():
    bp = ProjectBlueprint(
        project_name="test_proj",
        project_type=ProjectType.LIBRARY,
        description="Test",
        tech_stack=["Python"],
        file_structure=[FileSpec(path="lib.py", purpose="Core")],
        dependencies=[],
        key_features=["Feature 1"],
    )
    restored = ProjectBlueprint.model_validate_json(bp.model_dump_json())
    assert restored == bp


def test_implementation_phase():
    phase = ImplementationPhase(
        phase_number=1,
        title="Project setup",
        description="Initialize project structure",
        files_to_create=["pyproject.toml", "src/__init__.py"],
        depends_on_phases=[],
        commit_message="feat: initialize project scaffold",
    )
    assert phase.phase_number == 1
    assert len(phase.files_to_create) == 2


def test_planner_result():
    result = PlannerResult(
        phases=[
            ImplementationPhase(
                phase_number=1,
                title="Setup",
                description="Init",
                files_to_create=["setup.py"],
                commit_message="feat: init",
            )
        ],
        estimated_total_files=5,
        testing_strategy="pytest",
    )
    assert len(result.phases) == 1


def test_generated_file():
    gf = GeneratedFile(
        path="main.py",
        content='print("hello")',
        language="python",
    )
    assert gf.language == "python"


def test_phase_code_result():
    result = PhaseCodeResult(
        phase_number=1,
        files=[
            GeneratedFile(path="main.py", content="# main", language="python")
        ],
        test_files=[
            GeneratedFile(
                path="test_main.py", content="# test", language="python"
            )
        ],
    )
    assert len(result.files) == 1
    assert len(result.test_files) == 1


def test_phase_code_result_no_tests():
    result = PhaseCodeResult(
        phase_number=2,
        files=[
            GeneratedFile(path="config.py", content="# cfg", language="python")
        ],
    )
    assert result.test_files == []


def test_readme_result():
    result = ReadmeResult(content="# My Project\n\nA cool project.")
    assert result.content.startswith("# My Project")


def test_pipeline_run():
    run = PipelineRun(
        run_id="abc123",
        started_at=datetime(2026, 2, 25, 12, 0, 0),
    )
    assert run.status == PipelineStatus.RUNNING
    assert run.completed_at is None
    assert run.github_url is None


def test_pipeline_run_with_all_fields():
    idea = _make_idea()
    bp = ProjectBlueprint(
        project_name="test",
        project_type=ProjectType.CLI_TOOL,
        description="Test",
        tech_stack=["Python"],
        file_structure=[],
        dependencies=[],
        key_features=["F1"],
    )
    run = PipelineRun(
        run_id="xyz789",
        started_at=datetime(2026, 2, 25, 12, 0, 0),
        completed_at=datetime(2026, 2, 25, 13, 0, 0),
        status=PipelineStatus.COMPLETED,
        selected_idea=idea,
        blueprint=bp,
        github_url="https://github.com/user/test",
    )
    assert run.status == PipelineStatus.COMPLETED
    assert run.github_url is not None
