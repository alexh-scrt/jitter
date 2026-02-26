"""Shared test fixtures."""

from datetime import datetime

import pytest

from jitter.models import (
    FileSpec,
    GeneratedFile,
    ImplementationPhase,
    PipelineRun,
    PlannerResult,
    ProjectBlueprint,
    ProjectType,
    TrendingIdea,
)


@pytest.fixture
def sample_idea():
    return TrendingIdea(
        title="AI Code Reviewer",
        description="A CLI tool that reviews code diffs using AI and suggests improvements.",
        source_url="https://example.com/trending/ai-code-review",
        category="ai",
        buzz_score=8,
    )


@pytest.fixture
def sample_blueprint():
    return ProjectBlueprint(
        project_name="ai_code_reviewer",
        project_type=ProjectType.CLI_TOOL,
        description="A CLI tool that reviews code diffs and suggests improvements using AI.",
        tech_stack=["Python", "Click", "Rich"],
        file_structure=[
            FileSpec(path="pyproject.toml", purpose="Project metadata"),
            FileSpec(path="reviewer/__init__.py", purpose="Package init"),
            FileSpec(path="reviewer/main.py", purpose="CLI entry point"),
            FileSpec(path="reviewer/analyzer.py", purpose="Code analysis logic"),
            FileSpec(path="tests/test_analyzer.py", purpose="Analyzer tests"),
        ],
        dependencies=["click", "rich"],
        key_features=["Diff analysis", "AI suggestions", "Multiple languages"],
    )


@pytest.fixture
def sample_phases():
    return PlannerResult(
        phases=[
            ImplementationPhase(
                phase_number=1,
                title="Project setup",
                description="Initialize project structure and dependencies.",
                files_to_create=["pyproject.toml", "reviewer/__init__.py"],
                commit_message="feat: initialize project scaffold",
            ),
            ImplementationPhase(
                phase_number=2,
                title="Core logic",
                description="Implement code analysis functionality.",
                files_to_create=["reviewer/main.py", "reviewer/analyzer.py"],
                depends_on_phases=[1],
                commit_message="feat: add code analysis logic",
            ),
            ImplementationPhase(
                phase_number=3,
                title="Tests",
                description="Add unit tests.",
                files_to_create=["tests/test_analyzer.py"],
                depends_on_phases=[1, 2],
                commit_message="test: add unit tests for analyzer",
            ),
        ],
        estimated_total_files=5,
        testing_strategy="pytest with mocked AI calls",
    )


@pytest.fixture
def sample_generated_files():
    return [
        GeneratedFile(
            path="pyproject.toml",
            content='[project]\nname = "ai-code-reviewer"\n',
            language="toml",
        ),
        GeneratedFile(
            path="reviewer/__init__.py",
            content='"""AI Code Reviewer."""\n',
            language="python",
        ),
    ]


@pytest.fixture
def sample_run():
    return PipelineRun(
        run_id="test123",
        started_at=datetime(2026, 2, 25, 12, 0, 0),
    )
