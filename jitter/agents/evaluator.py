"""Evaluator agent: scores and selects the best idea to implement."""

from __future__ import annotations

import json

from jitter.config import JitterConfig
from jitter.models import EvaluatorResult, ScoutResult
from jitter.services.anthropic_client import AnthropicService
from jitter.utils.logging import get_logger

logger = get_logger("evaluator")

SYSTEM_PROMPT = """You are a senior developer evaluating project ideas for a daily coding challenge.
You must select the single BEST idea to build today.

Score each idea on three axes (1-10):
- Feasibility: Can this be built as a working prototype in under 500 lines of code?
  Consider: clear scope, well-understood problem, available libraries.
- Novelty: Is this a fresh take? NOT a rehash of common tutorials (todo apps, weather apps, etc.)
- Usefulness: Would real developers or users actually find this useful?

Overall score = (feasibility * 0.4) + (novelty * 0.3) + (usefulness * 0.3), rounded to nearest int.

Select the idea with the highest overall score. If there's a tie, prefer feasibility.
Explain your reasoning clearly."""


class EvaluatorAgent:
    """Evaluates discovered ideas and selects the best one."""

    def __init__(self, config: JitterConfig):
        self.anthropic = AnthropicService(
            config.anthropic_api_key, config.model_default
        )

    def evaluate(
        self,
        scout_result: ScoutResult,
        past_project_names: list[str],
        recent_categories: dict[str, int] | None = None,
    ) -> EvaluatorResult:
        """Score all ideas and select the best one.

        Args:
            scout_result: Ideas from the scout agent.
            past_project_names: Names of previously built projects.
            recent_categories: {category: count} for projects built in the
                              last few days (for category cooldown).
        """
        logger.info("Evaluating %d ideas...", len(scout_result.ideas))

        ideas_data = [idea.model_dump() for idea in scout_result.ideas]

        exclusion = ""
        if past_project_names:
            exclusion = (
                f"\n\nYou MUST NOT select any idea similar to these previously "
                f"built projects: {json.dumps(past_project_names)}"
            )

        cooldown = ""
        if recent_categories:
            cooldown = (
                f"\n\nIMPORTANT - Category cooldown: We recently built projects in these "
                f"categories (last 3 days): {json.dumps(recent_categories)}. "
                f"STRONGLY prefer ideas from DIFFERENT categories to ensure variety. "
                f"Penalize ideas in these categories by -2 on their novelty score."
            )

        user_message = (
            f"Evaluate these project ideas and select the best one:\n\n"
            f"{json.dumps(ideas_data, indent=2)}"
            f"{exclusion}"
            f"{cooldown}"
        )

        result = self.anthropic.generate_structured(
            system=SYSTEM_PROMPT,
            user_message=user_message,
            output_model=EvaluatorResult,
        )

        logger.info(
            "Selected: %s (score: %d) - %s",
            result.selected_idea.title,
            next(
                (e.overall_score for e in result.evaluations
                 if e.idea_title == result.selected_idea.title),
                0,
            ),
            result.selection_reasoning[:100],
        )
        return result
