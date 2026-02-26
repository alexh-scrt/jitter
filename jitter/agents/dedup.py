"""Dedup agent: uses Claude to detect semantic duplicates against past projects."""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from jitter.config import JitterConfig
from jitter.models import TrendingIdea
from jitter.services.anthropic_client import AnthropicService
from jitter.utils.logging import get_logger

logger = get_logger("dedup")

SYSTEM_PROMPT = """You are a duplicate-detection judge. Your job is to determine whether
a proposed project idea is too similar to any previously built project.

Two projects are "too similar" if:
- They solve the same core problem (even if named differently)
- One is a subset or minor variation of the other
- A user would consider them interchangeable

Two projects are NOT duplicates if:
- They share a technology but solve different problems
- They are in the same category but have distinct functionality
- They have similar names but do fundamentally different things

Be strict: if in doubt, flag it as a duplicate. We want variety."""


class DedupVerdict(BaseModel):
    """Result of the dedup judge check."""
    is_duplicate: bool = Field(
        description="True if the idea is too similar to a past project"
    )
    similar_to: str | None = Field(
        default=None,
        description="Title of the most similar past project, if duplicate"
    )
    reasoning: str = Field(
        description="Brief explanation of why this is or isn't a duplicate"
    )


class DedupAgent:
    """Uses Claude to semantically compare a new idea against past projects."""

    def __init__(self, config: JitterConfig):
        self.anthropic = AnthropicService(
            config.anthropic_api_key, config.model_default
        )

    def check(
        self,
        idea: TrendingIdea,
        past_projects: list[dict],
    ) -> DedupVerdict:
        """Check if an idea is a semantic duplicate of any past project.

        Args:
            idea: The candidate idea to check.
            past_projects: List of dicts with 'idea_title', 'description',
                          'idea_category' from the history store.
        Returns:
            DedupVerdict with is_duplicate, similar_to, and reasoning.
        """
        if not past_projects:
            logger.debug("No past projects to check against, skipping dedup")
            return DedupVerdict(
                is_duplicate=False,
                similar_to=None,
                reasoning="No past projects exist yet.",
            )

        logger.info("Checking idea '%s' against %d past projects", idea.title, len(past_projects))

        past_summary = json.dumps(past_projects, indent=2)

        user_message = (
            f"## Proposed New Idea\n"
            f"Title: {idea.title}\n"
            f"Description: {idea.description}\n"
            f"Category: {idea.category}\n\n"
            f"## Previously Built Projects\n"
            f"{past_summary}\n\n"
            f"Is the proposed idea too similar to any previously built project?"
        )

        verdict = self.anthropic.generate_structured(
            system=SYSTEM_PROMPT,
            user_message=user_message,
            output_model=DedupVerdict,
            max_tokens=1024,
        )

        if verdict.is_duplicate:
            logger.info(
                "DUPLICATE detected: '%s' similar to '%s' — %s",
                idea.title,
                verdict.similar_to,
                verdict.reasoning,
            )
        else:
            logger.debug("Idea '%s' is unique: %s", idea.title, verdict.reasoning)

        return verdict
