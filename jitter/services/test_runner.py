"""Runs generated project tests in an isolated temporary directory."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from jitter.models import GeneratedFile
from jitter.utils.logging import get_logger

logger = get_logger("test_runner")


class TestRunner:
    """Executes pytest on generated code in a temporary environment."""

    def __init__(self, timeout: int = 60):
        self.timeout = timeout

    def run_tests(
        self,
        files: list[GeneratedFile],
        dependencies: list[str],
    ) -> tuple[bool, str]:
        """Write files to a temp dir, install deps, run pytest.

        Returns (passed: bool, output: str).
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            project_dir = Path(tmpdir)

            # Write all files to the temp directory
            for f in files:
                file_path = project_dir / f.path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(f.content)
                logger.debug("Wrote: %s", f.path)

            # Install dependencies if any
            if dependencies:
                logger.info("Installing %d dependencies...", len(dependencies))
                dep_result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--quiet", *dependencies],
                    cwd=project_dir,
                    timeout=120,
                    capture_output=True,
                    text=True,
                )
                if dep_result.returncode != 0:
                    msg = f"Dependency install failed: {dep_result.stderr[:500]}"
                    logger.warning(msg)
                    return False, msg

            # Check if any test files exist
            test_files = list(project_dir.rglob("test_*.py"))
            if not test_files:
                logger.info("No test files found, skipping test run")
                return True, "No test files to run"

            # Run pytest
            logger.info("Running pytest on %d test files...", len(test_files))
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", "-x", "--tb=short", "-q"],
                    cwd=project_dir,
                    timeout=self.timeout,
                    capture_output=True,
                    text=True,
                )
                output = result.stdout + result.stderr
                passed = result.returncode == 0

                if passed:
                    logger.info("Tests passed")
                else:
                    logger.warning("Tests failed:\n%s", output[:500])

                return passed, output

            except subprocess.TimeoutExpired:
                msg = f"Tests timed out after {self.timeout}s"
                logger.warning(msg)
                return False, msg
