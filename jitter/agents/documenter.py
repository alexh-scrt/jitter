"""Documenter agent: generates a comprehensive README.md for the project."""

from __future__ import annotations

from jitter.config import JitterConfig
from jitter.models import GeneratedFile, ProjectBlueprint, ReadmeResult
from jitter.services.anthropic_client import AnthropicService
from jitter.utils.logging import get_logger

logger = get_logger("documenter")

SYSTEM_PROMPT = """You are a technical writer creating a README.md for an open-source project.

Include these sections:
1. Title with a short, catchy tagline
2. What it does (2-3 sentences, clear and engaging)
3. Quick Start (install + basic usage commands)
4. Features (bulleted list, 3-5 items)
5. Usage examples with realistic code blocks or CLI examples
6. Project structure (file tree)
7. Configuration (if the project has config options)
8. License: MIT

End with a note: "Built with [Jitter](https://github.com/jitter-ai) - an AI agent that ships code daily."

Keep the tone professional but approachable. Use clear, concise language.
The README should be practical - a developer should be able to use the project
after reading just the Quick Start section."""


class DocumenterAgent:
    """Generates a README.md for the completed project."""

    def __init__(self, config: JitterConfig):
        self.anthropic = AnthropicService(
            config.anthropic_api_key, config.model_default
        )

    def generate(
        self,
        blueprint: ProjectBlueprint,
        all_files: list[GeneratedFile],
    ) -> ReadmeResult:
        """Generate a comprehensive README based on the blueprint and generated code."""
        logger.info("Generating README for: %s", blueprint.project_name)

        # Build a summary of the code for context
        file_summaries = []
        for f in all_files:
            # Include first 20 lines of each file for context
            lines = f.content.split("\n")[:20]
            preview = "\n".join(lines)
            if len(f.content.split("\n")) > 20:
                preview += "\n... (more code)"
            file_summaries.append(f"### {f.path}\n```{f.language}\n{preview}\n```")

        user_message = (
            f"Generate a README.md for this project:\n\n"
            f"## Blueprint\n{blueprint.model_dump_json(indent=2)}\n\n"
            f"## Source Files\n" + "\n\n".join(file_summaries)
        )

        result = self.anthropic.generate_structured(
            system=SYSTEM_PROMPT,
            user_message=user_message,
            output_model=ReadmeResult,
        )

        logger.info("README generated (%d chars)", len(result.content))
        return result
