"""GitHub integration using PyGithub for repo creation and Git Data API commits."""

from __future__ import annotations

import time

from github import Github, GithubException, InputGitTreeElement
from github.Repository import Repository

from jitter.models import GeneratedFile
from jitter.utils.logging import get_logger

logger = get_logger("github_service")


class GitHubService:
    """Creates repos and pushes multi-file commits via the Git Data API."""

    def __init__(self, token: str, org: str | None = None):
        self.gh = Github(token)
        self.org = org
        if org:
            self._owner = self.gh.get_organization(org)
        else:
            self._owner = self.gh.get_user()

    def create_repo(
        self,
        name: str,
        description: str,
        private: bool = False,
        topics: list[str] | None = None,
    ) -> Repository:
        """Create a new GitHub repository with an initial commit."""
        logger.info("Creating repo: %s", name)

        repo = self._owner.create_repo(
            name=name,
            description=description[:350],
            private=private,
            auto_init=True,
        )

        if topics:
            repo.replace_topics(topics)

        # Wait for auto_init to finish — GitHub creates the initial commit
        # asynchronously and the default branch ref may not exist yet.
        self._wait_for_default_branch(repo)

        logger.info("Repo created: %s (branch: %s)", repo.html_url, repo.default_branch)
        return repo

    def push_files(
        self,
        repo: Repository,
        files: list[GeneratedFile],
        commit_message: str,
        branch: str | None = None,
    ) -> str:
        """Push multiple files in a single atomic commit using Git Data API.

        Uses the blob-first approach: each file is created as a Git blob,
        then blob SHAs are referenced in the tree.  This avoids the ~100 KB
        inline-content limit on ``create_git_tree`` and handles encoding
        edge-cases that can cause 404 errors with inline content.

        Uses the repo's default branch if no branch is specified.
        Returns the new commit SHA.
        """
        if not files:
            logger.warning("No files to push, skipping commit")
            return ""

        # Filter out files with empty paths or content
        valid_files = [f for f in files if f.path and f.path.strip() and f.content]
        if not valid_files:
            logger.warning("No valid files to push after filtering, skipping commit")
            return ""

        # Use the repo's actual default branch (main, master, etc.)
        if branch is None:
            branch = repo.default_branch

        # Get current branch head
        ref = repo.get_git_ref(f"heads/{branch}")
        latest_commit = repo.get_git_commit(ref.object.sha)
        base_tree = latest_commit.tree

        # Create blobs first, then reference them in the tree.
        # This is more robust than inline content because:
        # 1. No ~100 KB size limit per file
        # 2. Proper UTF-8 encoding handled by the blob endpoint
        # 3. Avoids 404 errors from malformed inline content
        tree_elements = []
        for f in valid_files:
            blob = repo.create_git_blob(f.content, "utf-8")
            logger.debug("Created blob for %s: %s", f.path, blob.sha[:7])
            element = InputGitTreeElement(
                path=f.path,
                mode="100644",
                type="blob",
                sha=blob.sha,
            )
            tree_elements.append(element)

        # Create new tree, commit, and update ref
        new_tree = repo.create_git_tree(tree_elements, base_tree)
        new_commit = repo.create_git_commit(
            message=commit_message,
            tree=new_tree,
            parents=[latest_commit],
        )
        # force=True avoids "not a fast forward" errors when the ref
        # hasn't fully propagated from a prior push in the same loop.
        # Safe because we're the sole writer to this new repo.
        ref.edit(new_commit.sha, force=True)

        logger.info(
            "Pushed %d files: %s (%s)",
            len(valid_files),
            commit_message,
            new_commit.sha[:7],
        )
        return new_commit.sha

    def _wait_for_default_branch(self, repo: Repository, max_wait: int = 15) -> None:
        """Poll until the default branch ref exists after auto_init.

        GitHub creates the initial commit asynchronously. This waits up to
        max_wait seconds for the ref to become available.
        """
        branch = repo.default_branch
        for attempt in range(max_wait):
            try:
                repo.get_git_ref(f"heads/{branch}")
                logger.debug("Default branch '%s' ready (attempt %d)", branch, attempt + 1)
                return
            except GithubException as e:
                if e.status == 404:
                    logger.debug(
                        "Waiting for default branch '%s' (attempt %d/%d)...",
                        branch,
                        attempt + 1,
                        max_wait,
                    )
                    time.sleep(1)
                else:
                    raise

        raise RuntimeError(
            f"Default branch '{branch}' not available after {max_wait}s. "
            f"auto_init may have failed for repo {repo.full_name}."
        )
