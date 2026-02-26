"""Planner agent: breaks a project blueprint into implementation phases."""

from __future__ import annotations

from jitter.config import JitterConfig
from jitter.models import PlannerResult, ProjectBlueprint
from jitter.services.anthropic_client import AnthropicService
from jitter.utils.logging import get_logger

logger = get_logger("planner")

SYSTEM_PROMPT = """You are a project planner breaking a software project into implementation phases.
Each phase should result in a meaningful git commit with working code.

Rules:
- Create {max_phases} phases maximum
- Each phase should touch 1-{max_files} files
- Phase 1 MUST be project setup: pyproject.toml/requirements.txt, __init__.py, basic structure
- Each phase must build on previous phases (no forward references to unwritten code)
- Code in each phase should at minimum parse/import without errors
- Use conventional commit messages: "feat:", "test:", "docs:", "fix:", "chore:"
- Spread implementation logically:
  - Early phases: scaffold, data models, core abstractions
  - Middle phases: business logic, main features
  - Later phases: CLI/API layer, tests, error handling
- The final phase should be polish/integration
- Keep depends_on_phases accurate - list all phases whose code is imported or referenced"""


class PlannerAgent:
    """Breaks a project blueprint into ordered implementation phases."""

    def __init__(self, config: JitterConfig):
        self.config = config
        self.anthropic = AnthropicService(
            config.anthropic_api_key, config.model_default
        )

    def plan(self, blueprint: ProjectBlueprint) -> PlannerResult:
        """Generate implementation phases for the given blueprint."""
        logger.info("Planning phases for: %s", blueprint.project_name)

        system = SYSTEM_PROMPT.format(
            max_phases=self.config.pipeline_max_phases,
            max_files=self.config.pipeline_max_files_per_phase,
        )

        user_message = (
            f"Break this project into implementation phases:\n\n"
            f"{blueprint.model_dump_json(indent=2)}"
        )

        result = self.anthropic.generate_structured(
            system=system,
            user_message=user_message,
            output_model=PlannerResult,
        )

        # Enforce max phases
        if len(result.phases) > self.config.pipeline_max_phases:
            result.phases = result.phases[: self.config.pipeline_max_phases]

        logger.info(
            "Planned %d phases, ~%d total files",
            len(result.phases),
            result.estimated_total_files,
        )
        return result
