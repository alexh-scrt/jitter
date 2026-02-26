"""Main pipeline orchestrator: wires all agents together for a daily run."""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from jitter.agents.architect import ArchitectAgent
from jitter.agents.coder import CoderAgent
from jitter.agents.dedup import DedupAgent
from jitter.agents.documenter import DocumenterAgent
from jitter.agents.evaluator import EvaluatorAgent
from jitter.agents.planner import PlannerAgent
from jitter.agents.scout import ScoutAgent
from jitter.config import JitterConfig
from jitter.models import GeneratedFile, PipelineRun, PipelineStatus, TrendingIdea
from jitter.services.github_service import GitHubService
from jitter.services.test_runner import TestRunner
from jitter.store.history import HistoryStore
from jitter.utils.logging import get_logger

logger = get_logger("pipeline")

MAX_DEDUP_RETRIES = 3


class Pipeline:
    """Orchestrates the full daily pipeline from discovery to deployment."""

    def __init__(self, config: JitterConfig, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self.history = HistoryStore(config.history_db_path)
        self.test_runner = TestRunner(config.pipeline_test_timeout_seconds)

        if not dry_run and config.github_token:
            self.github = GitHubService(config.github_token, config.github_org)
        else:
            self.github = None

    def run(self) -> PipelineRun:
        """Execute the full pipeline end-to-end."""
        run = PipelineRun(
            run_id=str(uuid.uuid4())[:8],
            started_at=datetime.now(),
        )
        self.history.record_run_start(run)

        try:
            # Step 1: Scout for trending ideas
            logger.info("[1/8] Scouting for trending ideas...")
            scout = ScoutAgent(self.config)
            past_titles = self.history.get_past_idea_titles()
            scout_result = scout.search(past_idea_titles=past_titles)
            logger.info("Found %d ideas", len(scout_result.ideas))

            # Step 1.5: Layer 1 — Pre-filter fuzzy duplicates
            filtered_ideas = self._filter_fuzzy_duplicates(scout_result.ideas)
            if not filtered_ideas:
                raise RuntimeError(
                    "All scouted ideas are duplicates of past projects. "
                    "Try adding more search queries to config.yaml."
                )
            scout_result.ideas = filtered_ideas
            logger.info("%d ideas remain after fuzzy dedup", len(filtered_ideas))

            # Step 2: Evaluate and select (with Layer 4 — category cooldown)
            logger.info("[2/8] Evaluating ideas...")
            selected_idea = self._evaluate_with_dedup(scout_result)
            run.selected_idea = selected_idea
            self.history.update_run_idea(run.run_id, selected_idea)
            logger.info("Selected (dedup-verified): %s", selected_idea.title)

            # Step 3: Design the project blueprint
            logger.info("[3/8] Designing blueprint...")
            architect = ArchitectAgent(self.config)
            blueprint = architect.design(selected_idea)
            run.blueprint = blueprint
            self.history.update_run_blueprint(run.run_id, blueprint)
            logger.info(
                "Blueprint: %s (%s, %d files)",
                blueprint.project_name,
                blueprint.project_type.value,
                len(blueprint.file_structure),
            )

            # Step 4: Break into implementation phases
            logger.info("[4/8] Planning implementation phases...")
            planner = PlannerAgent(self.config)
            plan = planner.plan(blueprint)
            logger.info("Planned %d phases", len(plan.phases))

            # Step 5: Generate code phase by phase
            logger.info("[5/8] Generating code...")
            coder = CoderAgent(self.config)
            all_phase_results = []
            accumulated_files: list[GeneratedFile] = []

            for phase in plan.phases:
                logger.info(
                    "  Phase %d/%d: %s",
                    phase.phase_number,
                    len(plan.phases),
                    phase.title,
                )

                phase_result = coder.generate(
                    blueprint, plan, phase, accumulated_files
                )

                # Accumulate files for context in next phase
                accumulated_files.extend(phase_result.files)
                accumulated_files.extend(phase_result.test_files)
                all_phase_results.append(phase_result)

            # Step 6: Run tests
            logger.info("[6/8] Running tests...")
            all_files = []
            for pr in all_phase_results:
                all_files.extend(pr.files)
                all_files.extend(pr.test_files)

            test_passed, test_output = self.test_runner.run_tests(
                all_files, blueprint.dependencies
            )
            if test_passed:
                logger.info("Tests passed!")
            else:
                logger.warning("Tests failed (non-blocking): %s", test_output[:300])

            # Step 7: Generate README
            logger.info("[7/8] Generating README...")
            documenter = DocumenterAgent(self.config)
            readme = documenter.generate(blueprint, all_files)

            # Optionally save to local output directory
            self._save_locally(blueprint.project_name, all_files, readme.content)

            # Step 8: Push to GitHub
            github_url = None
            if self.github and not self.dry_run:
                logger.info("[8/8] Pushing to GitHub...")
                github_url = self._push_to_github(
                    blueprint, plan, all_phase_results, readme.content
                )
                logger.info("Published: %s", github_url)
            else:
                logger.info("[8/8] Dry run - skipping GitHub push")

            # Record success
            run.github_url = github_url
            run.status = PipelineStatus.COMPLETED
            run.completed_at = datetime.now()

            self.history.record_run_complete(
                run.run_id, github_url or "dry-run"
            )
            self.history.record_built_project(
                run.run_id,
                blueprint,
                selected_idea,
                github_url,
            )

            elapsed = (run.completed_at - run.started_at).total_seconds()
            logger.info(
                "Pipeline completed in %.1fs: %s -> %s",
                elapsed,
                blueprint.project_name,
                github_url or "(dry run)",
            )
            return run

        except Exception as e:
            run.status = PipelineStatus.FAILED
            run.error = str(e)
            run.completed_at = datetime.now()
            self.history.record_run_failed(run.run_id, str(e))
            logger.error("Pipeline failed: %s", e, exc_info=True)
            raise

    def _filter_fuzzy_duplicates(self, ideas: list[TrendingIdea]) -> list[TrendingIdea]:
        """Layer 1: Remove ideas that fuzzy-match past projects."""
        filtered = []
        for idea in ideas:
            is_dup, match = self.history.is_fuzzy_duplicate(idea.title)
            if is_dup:
                logger.info(
                    "Fuzzy dedup: dropping '%s' (matches '%s')", idea.title, match
                )
            else:
                filtered.append(idea)
        return filtered

    def _evaluate_with_dedup(self, scout_result) -> TrendingIdea:
        """Evaluate ideas with Layer 3 (Claude judge) and Layer 4 (category cooldown).

        If the top pick is flagged as a duplicate, tries the next-best idea
        from the evaluations, up to MAX_DEDUP_RETRIES times.
        """
        evaluator = EvaluatorAgent(self.config)
        dedup = DedupAgent(self.config)

        past_names = self.history.get_past_project_names()
        recent_cats = self.history.get_recent_categories(days=3)
        past_summaries = self.history.get_past_projects_summary()

        # Layer 4: category cooldown is baked into the evaluator prompt
        eval_result = evaluator.evaluate(scout_result, past_names, recent_cats)

        # Layer 3: Claude dedup judge checks the selected idea
        # Sort evaluations by score descending to try alternatives
        ranked = sorted(
            eval_result.evaluations,
            key=lambda e: e.overall_score,
            reverse=True,
        )

        rejected_titles: set[str] = set()

        for attempt in range(MAX_DEDUP_RETRIES + 1):
            candidate = eval_result.selected_idea

            # On retries, pick the next-best idea that hasn't been rejected
            if attempt > 0:
                candidate = None
                for ev in ranked:
                    if ev.idea_title not in rejected_titles:
                        # Find the matching TrendingIdea from scout results
                        for idea in scout_result.ideas:
                            if idea.title == ev.idea_title:
                                candidate = idea
                                break
                        if candidate:
                            break

                if candidate is None:
                    raise RuntimeError(
                        f"All {len(scout_result.ideas)} ideas were flagged as duplicates. "
                        f"Rejected: {rejected_titles}"
                    )

            # Check with Claude dedup judge
            verdict = dedup.check(candidate, past_summaries)

            if not verdict.is_duplicate:
                if attempt > 0:
                    logger.info(
                        "Dedup retry %d: accepted '%s'", attempt, candidate.title
                    )
                return candidate

            # Flagged as duplicate — reject and try next
            logger.warning(
                "Dedup attempt %d: '%s' flagged as duplicate of '%s'",
                attempt + 1,
                candidate.title,
                verdict.similar_to,
            )
            rejected_titles.add(candidate.title)

        raise RuntimeError(
            f"Could not find a unique idea after {MAX_DEDUP_RETRIES + 1} attempts. "
            f"Rejected: {rejected_titles}"
        )

    def _push_to_github(self, blueprint, plan, all_phase_results, readme_content):
        """Create repo and push each phase as a separate commit."""
        repo_name = blueprint.project_name.replace("_", "-")
        repo = self.github.create_repo(
            name=repo_name,
            description=blueprint.description[:350],
            private=self.config.github_private,
            topics=self.config.github_topic_tags,
        )

        # Push each phase as a separate commit
        for phase, phase_result in zip(plan.phases, all_phase_results):
            files_to_push = phase_result.files + phase_result.test_files
            if files_to_push:
                self.github.push_files(repo, files_to_push, phase.commit_message)

        # Push README as final commit
        readme_file = GeneratedFile(
            path="README.md",
            content=readme_content,
            language="markdown",
        )
        self.github.push_files(repo, [readme_file], "docs: add comprehensive README")

        return repo.html_url

    def _save_locally(self, project_name, files, readme_content):
        """Save generated files to the configured output directory."""
        output_dir = Path(self.config.output_dir) / project_name
        output_dir.mkdir(parents=True, exist_ok=True)

        for f in files:
            file_path = output_dir / f.path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f.content)

        readme_path = output_dir / "README.md"
        readme_path.write_text(readme_content)

        logger.info("Saved locally to: %s", output_dir)
