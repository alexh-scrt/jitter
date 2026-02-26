"""Pydantic data models for all pipeline stages.

These models serve dual purpose:
1. Internal data passing between pipeline stages
2. Structured output schemas for Claude's messages.parse()
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# --- Scout output ---


class TrendingIdea(BaseModel):
    """A single trending idea discovered by the scout."""

    title: str = Field(description="Short title of the trending idea")
    description: str = Field(description="2-3 sentence description of the idea")
    source_url: str = Field(description="URL where this idea was found")
    category: str = Field(
        description="Category: ai, web, devtools, data, security, automation, etc."
    )
    buzz_score: int = Field(
        description="Estimated buzz/trendiness score from 1 (low) to 10 (high)"
    )


class ScoutResult(BaseModel):
    """Output of the scout agent: a collection of trending ideas."""

    ideas: list[TrendingIdea] = Field(
        description="List of discovered trending ideas, scored and deduplicated"
    )
    search_queries_used: list[str] = Field(
        description="The search queries that were used to find these ideas"
    )


# --- Evaluator output ---


class IdeaEvaluation(BaseModel):
    """Evaluation of a single idea across multiple criteria."""

    idea_title: str = Field(description="Title of the idea being evaluated")
    feasibility_score: int = Field(
        description="How feasible to build as a prototype in a day, 1-10"
    )
    novelty_score: int = Field(
        description="How novel/original the idea is, 1-10"
    )
    usefulness_score: int = Field(
        description="How useful to developers or end users, 1-10"
    )
    overall_score: int = Field(description="Weighted overall score, 1-10")
    reasoning: str = Field(description="Brief explanation of the scores")


class EvaluatorResult(BaseModel):
    """Output of the evaluator agent: scored ideas with a selection."""

    evaluations: list[IdeaEvaluation] = Field(
        description="Evaluation of each candidate idea"
    )
    selected_idea: TrendingIdea = Field(
        description="The best idea selected for implementation"
    )
    selection_reasoning: str = Field(
        description="Why this idea was chosen over the others"
    )


# --- Architect output ---


class ProjectType(str, Enum):
    """Type of project to build."""

    CLI_TOOL = "cli_tool"
    API_SERVER = "api_server"
    LIBRARY = "library"
    WEB_APP = "web_app"
    EXTENSION = "extension"
    SCRIPT = "script"


class FileSpec(BaseModel):
    """Specification for a single file in the project."""

    path: str = Field(description="Relative file path within the project")
    purpose: str = Field(description="What this file does in one sentence")


class ProjectBlueprint(BaseModel):
    """Complete design blueprint for a project."""

    project_name: str = Field(
        description="Short snake_case project name, e.g. 'trend_tracker'"
    )
    project_type: ProjectType = Field(description="Type of project")
    description: str = Field(
        description="One-paragraph project description for the README"
    )
    tech_stack: list[str] = Field(
        description="Technologies and libraries to use, e.g. ['Python', 'FastAPI', 'SQLite']"
    )
    file_structure: list[FileSpec] = Field(
        description="All files that will exist in the project"
    )
    dependencies: list[str] = Field(
        description="pip package names for requirements.txt"
    )
    key_features: list[str] = Field(description="3-5 key features of the project")


# --- Planner output ---


class ImplementationPhase(BaseModel):
    """A single implementation phase with files and commit info."""

    phase_number: int = Field(description="Phase number, starting from 1")
    title: str = Field(description="Short title like 'Core data models'")
    description: str = Field(
        description="What this phase accomplishes in 1-2 sentences"
    )
    files_to_create: list[str] = Field(
        description="Relative file paths to create or modify in this phase"
    )
    depends_on_phases: list[int] = Field(
        default_factory=list,
        description="Phase numbers this phase depends on (empty for phase 1)",
    )
    commit_message: str = Field(
        description="Conventional git commit message, e.g. 'feat: add core data models'"
    )


class PlannerResult(BaseModel):
    """Output of the planner agent: ordered implementation phases."""

    phases: list[ImplementationPhase] = Field(
        description="Ordered list of implementation phases"
    )
    estimated_total_files: int = Field(
        description="Total number of files across all phases"
    )
    testing_strategy: str = Field(
        description="Brief description of how the project should be tested"
    )


# --- Coder output ---


class GeneratedFile(BaseModel):
    """A single generated source file."""

    path: str = Field(description="Relative file path within the project")
    content: str = Field(description="Complete file content")
    language: str = Field(
        description="Programming language, e.g. 'python', 'javascript', 'markdown'"
    )


class PhaseCodeResult(BaseModel):
    """Output of the coder agent for a single phase."""

    phase_number: int = Field(description="The phase this code belongs to")
    files: list[GeneratedFile] = Field(
        description="Implementation files generated for this phase"
    )
    test_files: list[GeneratedFile] = Field(
        default_factory=list,
        description="Test files generated for this phase (if applicable)",
    )


# --- Documenter output ---


class ReadmeResult(BaseModel):
    """Output of the documenter agent."""

    content: str = Field(description="Complete README.md content in markdown")


# --- Pipeline tracking ---


class PipelineStatus(str, Enum):
    """Status of a pipeline run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineRun(BaseModel):
    """Tracks a single pipeline execution."""

    run_id: str = Field(description="Unique run identifier")
    started_at: datetime = Field(description="When the run started")
    completed_at: datetime | None = None
    status: PipelineStatus = PipelineStatus.RUNNING
    selected_idea: TrendingIdea | None = None
    blueprint: ProjectBlueprint | None = None
    github_url: str | None = None
    error: str | None = None
