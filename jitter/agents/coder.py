"""Coder agent: generates complete code for each implementation phase.

This is the most critical agent. It maintains context across phases by
including all previously generated files in each prompt, so Claude can
see the full project state and write coherent, interconnected code.

When a phase has too many files and the output gets truncated, it falls
back to generating files one at a time.
"""

from __future__ import annotations

import json

from jitter.config import JitterConfig
from jitter.models import (
    GeneratedFile,
    ImplementationPhase,
    PhaseCodeResult,
    PlannerResult,
    ProjectBlueprint,
)
from jitter.services.anthropic_client import AnthropicService, OutputTruncatedError
from jitter.utils.logging import get_logger

logger = get_logger("coder")

SYSTEM_PROMPT = """You are an expert software developer generating production-quality code.
You are implementing phase {phase_num} of {total_phases} for the project "{project_name}".

CRITICAL RULES:
- Generate COMPLETE file contents - never use placeholder comments like "# TODO" or "# ..."
- Every function must have a real implementation, not stubs
- Follow PEP 8 style and use type hints for all function signatures
- Include docstrings for all public functions and classes
- Handle errors gracefully with specific exception types
- Import only from stdlib or the project's declared dependencies: {dependencies}
- If generating test files, use pytest conventions (test_ prefix, assert statements)
- Code must work on first run - no missing imports, no undefined references
- Build on the existing code from previous phases - import from existing modules
- Each file must start with a module docstring

The project uses these dependencies: {dependencies}

IMPORTANT: Only generate files listed in the current phase. Do not regenerate files
from previous phases unless they need modification."""

SINGLE_FILE_SYSTEM_PROMPT = """You are an expert software developer generating production-quality code.
You are implementing a SINGLE FILE for the project "{project_name}".

CRITICAL RULES:
- Generate the COMPLETE file contents - never use placeholder comments like "# TODO" or "# ..."
- Every function must have a real implementation, not stubs
- Follow PEP 8 style and use type hints for all function signatures
- Include docstrings for all public functions and classes
- Handle errors gracefully with specific exception types
- Import only from stdlib or the project's declared dependencies: {dependencies}
- If generating a test file, use pytest conventions (test_ prefix, assert statements)
- Code must work on first run - no missing imports, no undefined references
- Build on the existing code from previous phases - import from existing modules
- The file must start with a module docstring

The project uses these dependencies: {dependencies}"""


class CoderAgent:
    """Generates code for each implementation phase with full context."""

    def __init__(self, config: JitterConfig):
        self.config = config
        self.anthropic = AnthropicService(
            config.anthropic_api_key, config.model_default
        )

    def generate(
        self,
        blueprint: ProjectBlueprint,
        plan: PlannerResult,
        phase: ImplementationPhase,
        accumulated_files: list[GeneratedFile],
    ) -> PhaseCodeResult:
        """Generate code for a single phase, with prior phases as context.

        If the batch generation is truncated, falls back to one-file-at-a-time.
        """
        logger.info(
            "Generating phase %d/%d: %s (%d files)",
            phase.phase_number,
            len(plan.phases),
            phase.title,
            len(phase.files_to_create),
        )

        # Try batch generation first (all files in one call)
        try:
            result = self._generate_batch(blueprint, plan, phase, accumulated_files)
            logger.info(
                "Generated %d implementation files + %d test files for phase %d",
                len(result.files),
                len(result.test_files),
                phase.phase_number,
            )
            return result

        except OutputTruncatedError as e:
            logger.warning(
                "Phase %d output truncated (%s). Falling back to per-file generation.",
                phase.phase_number,
                e,
            )
            return self._generate_per_file(blueprint, plan, phase, accumulated_files)

    def _generate_batch(
        self,
        blueprint: ProjectBlueprint,
        plan: PlannerResult,
        phase: ImplementationPhase,
        accumulated_files: list[GeneratedFile],
    ) -> PhaseCodeResult:
        """Generate all files for a phase in a single API call."""
        system = SYSTEM_PROMPT.format(
            phase_num=phase.phase_number,
            total_phases=len(plan.phases),
            project_name=blueprint.project_name,
            dependencies=", ".join(blueprint.dependencies) if blueprint.dependencies else "stdlib only",
        )

        user_message = self._build_context(blueprint, plan, phase, accumulated_files)

        result = self.anthropic.generate_structured(
            system=system,
            user_message=user_message,
            output_model=PhaseCodeResult,
            max_tokens=self.config.model_max_tokens,
        )

        result.phase_number = phase.phase_number
        return result

    def _generate_per_file(
        self,
        blueprint: ProjectBlueprint,
        plan: PlannerResult,
        phase: ImplementationPhase,
        accumulated_files: list[GeneratedFile],
    ) -> PhaseCodeResult:
        """Fallback: generate each file individually to avoid truncation."""
        system = SINGLE_FILE_SYSTEM_PROMPT.format(
            project_name=blueprint.project_name,
            dependencies=", ".join(blueprint.dependencies) if blueprint.dependencies else "stdlib only",
        )

        all_files: list[GeneratedFile] = []
        test_files: list[GeneratedFile] = []

        # Build shared context once (blueprint + accumulated files)
        context_parts = self._build_context_parts(blueprint, plan, phase, accumulated_files)
        base_context = "\n".join(context_parts)

        for file_path in phase.files_to_create:
            logger.info("  Generating single file: %s", file_path)

            # Include files we've already generated in THIS phase too
            extra_context = ""
            if all_files or test_files:
                extra_parts = ["\n## Files already generated in this phase:"]
                for f in all_files + test_files:
                    extra_parts.append(f"\n### {f.path}")
                    extra_parts.append(f"```{f.language}")
                    extra_parts.append(f.content)
                    extra_parts.append("```")
                extra_context = "\n".join(extra_parts)

            user_message = (
                f"{base_context}"
                f"{extra_context}\n\n"
                f"## File to Generate\n"
                f"Generate ONLY the file: `{file_path}`\n\n"
                f"Respond with the complete file content."
            )

            # For single file, use GeneratedFile directly
            result = self.anthropic.generate_structured(
                system=system,
                user_message=user_message,
                output_model=GeneratedFile,
                max_tokens=self.config.model_max_tokens,
            )

            # Ensure path matches what was requested
            result.path = file_path

            # Sort into implementation vs test files
            is_test = (
                "test_" in file_path.split("/")[-1]
                or "/tests/" in file_path
                or file_path.startswith("tests/")
            )
            if is_test:
                test_files.append(result)
            else:
                all_files.append(result)

        logger.info(
            "Per-file generation complete: %d impl + %d test files for phase %d",
            len(all_files),
            len(test_files),
            phase.phase_number,
        )

        return PhaseCodeResult(
            phase_number=phase.phase_number,
            files=all_files,
            test_files=test_files,
        )

    def _build_context(
        self,
        blueprint: ProjectBlueprint,
        plan: PlannerResult,
        phase: ImplementationPhase,
        accumulated_files: list[GeneratedFile],
    ) -> str:
        """Build the full user message with context for batch generation."""
        parts = self._build_context_parts(blueprint, plan, phase, accumulated_files)

        # Add current phase details
        parts.append("\n## Current Phase to Implement")
        parts.append(f"Phase {phase.phase_number}: {phase.title}")
        parts.append(f"Description: {phase.description}")
        parts.append(f"Files to generate: {json.dumps(phase.files_to_create)}")
        parts.append(
            "\nGenerate complete, working code for each file listed above."
        )

        return "\n".join(parts)

    def _build_context_parts(
        self,
        blueprint: ProjectBlueprint,
        plan: PlannerResult,
        phase: ImplementationPhase,
        accumulated_files: list[GeneratedFile],
    ) -> list[str]:
        """Build shared context parts (blueprint + plan + accumulated files)."""
        parts = []

        # Project blueprint (always included)
        parts.append("## Project Blueprint")
        parts.append(blueprint.model_dump_json(indent=2))

        # Full implementation plan for reference
        parts.append("\n## Full Implementation Plan")
        for p in plan.phases:
            marker = ">>> CURRENT" if p.phase_number == phase.phase_number else ""
            parts.append(
                f"  Phase {p.phase_number}: {p.title} - {p.description} {marker}"
            )

        # Previously generated files (accumulated context)
        if accumulated_files:
            parts.append("\n## Previously Generated Files (current project state)")
            files_to_include = accumulated_files

            if len(accumulated_files) > 20:
                # Summarize older files, show recent ones in full
                parts.append(
                    f"(Showing {len(accumulated_files)} files from prior phases)"
                )
                for f in accumulated_files[:10]:
                    parts.append(f"\n### {f.path} (summarized)")
                    lines = f.content.split("\n")[:30]
                    parts.append("```" + f.language)
                    parts.append("\n".join(lines))
                    if len(f.content.split("\n")) > 30:
                        parts.append("... (truncated)")
                    parts.append("```")
                files_to_include = accumulated_files[10:]

            for f in files_to_include:
                parts.append(f"\n### {f.path}")
                parts.append("```" + f.language)
                parts.append(f.content)
                parts.append("```")

        return parts
