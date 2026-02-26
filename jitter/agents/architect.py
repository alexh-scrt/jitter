"""Architect agent: designs a complete project blueprint for the selected idea."""

from __future__ import annotations

from jitter.config import JitterConfig
from jitter.models import ProjectBlueprint, TrendingIdea
from jitter.services.anthropic_client import AnthropicService
from jitter.utils.logging import get_logger

logger = get_logger("architect")

SYSTEM_PROMPT = """You are a software architect designing a small, focused project.
Given a trending idea, produce a complete project blueprint.

Rules:
- Keep the project to 5-15 source files maximum
- Use Python unless the idea specifically calls for another language
- Include a pyproject.toml or requirements.txt in the file structure
- Design for clarity and testability - simple, flat module structure
- project_name should be short, memorable, and snake_case (e.g., "trend_watcher")
- Include test files in the file structure
- Keep dependencies minimal - prefer stdlib where possible
- The project should be buildable by a single developer in one session
- Focus on a working MVP, not a complete product
- Include an __init__.py for the main package
- Pick the right project_type from: cli_tool, api_server, library, web_app, extension, script"""


class ArchitectAgent:
    """Designs a project blueprint from a trending idea."""

    def __init__(self, config: JitterConfig):
        self.anthropic = AnthropicService(
            config.anthropic_api_key, config.model_default
        )

    def design(self, idea: TrendingIdea) -> ProjectBlueprint:
        """Generate a complete project blueprint for the given idea."""
        logger.info("Designing blueprint for: %s", idea.title)

        user_message = (
            f"Design a project blueprint for this trending idea:\n\n"
            f"Title: {idea.title}\n"
            f"Description: {idea.description}\n"
            f"Category: {idea.category}\n\n"
            f"Create a complete, buildable project design."
        )

        blueprint = self.anthropic.generate_structured(
            system=SYSTEM_PROMPT,
            user_message=user_message,
            output_model=ProjectBlueprint,
        )

        logger.info(
            "Blueprint: %s (%s) - %d files, %d deps",
            blueprint.project_name,
            blueprint.project_type.value,
            len(blueprint.file_structure),
            len(blueprint.dependencies),
        )
        return blueprint
