"""Read recent Git commits and diffs. This tool does not modify the repository."""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.dependencies import DIFF_CHAR_LIMIT, repo_root, truncate

_MAX_COMMITS = 20
_DEFAULT_IMPACT_COMMITS = 5


def get_recent_changes(limit: int = 5) -> dict:
    """Return recent commits with per-commit patches plus any uncommitted diff.

    Review every patch in `recent_commit_diffs`, not only `latest_diff`. Older
    commits in the window can hold logic or formula regressions that the tip
    commit does not show. Use the diffs to spot unintended formula or logic
    changes, deleted or missing functions, and other code-level regressions—
    not only schema edits. `limit` is capped at 20. Patch text is truncated so
    a tool response stays small enough for the agent to read.
    """
    import git

    bounded = min(max(int(limit), 1), _MAX_COMMITS)
    try:
        repo = git.Repo(repo_root())
    except git.InvalidGitRepositoryError:
        return {
            "ok": False,
            "error": f"{repo_root()} is not a Git repository",
            "recent_commits": [],
            "recent_commit_diffs": [],
        }

    try:
        branch = repo.active_branch.name
    except TypeError:
        branch = "HEAD"

    commits = []
    for commit in repo.iter_commits(max_count=bounded):
        commits.append(
            {
                "sha": commit.hexsha,
                "short_sha": commit.hexsha[:7],
                "author": commit.author.name,
                "committed_at": commit.committed_datetime.isoformat(),
                "subject": commit.summary,
                "files": sorted(commit.stats.files),
            }
        )

    per_commit_limit = max(2_000, DIFF_CHAR_LIMIT // max(len(commits), 1))
    recent_commit_diffs = []
    for entry in commits:
        patch = truncate(
            repo.git.show("--format=", "--patch", entry["sha"]),
            per_commit_limit,
        )
        recent_commit_diffs.append(
            {
                "sha": entry["sha"],
                "short_sha": entry["short_sha"],
                "subject": entry["subject"],
                "files": entry["files"],
                "patch": patch,
            }
        )

    latest_diff = recent_commit_diffs[0]["patch"] if recent_commit_diffs else ""

    working_tree_diff = truncate(repo.git.diff("HEAD"))
    staged_diff = truncate(repo.git.diff("--cached"))

    return {
        "ok": True,
        "error": None,
        "repo_root": str(repo_root()),
        "branch": branch,
        "head": repo.head.commit.hexsha,
        "working_tree_dirty": repo.is_dirty(untracked_files=True),
        "staged_files": _name_only(repo, cached=True),
        "unstaged_files": _name_only(repo, cached=False),
        "recent_commits": commits,
        "recent_commit_diffs": recent_commit_diffs,
        "latest_diff": latest_diff,
        "staged_diff": staged_diff,
        "working_tree_diff": working_tree_diff,
    }


def changed_files_for_impact(commit_limit: int = _DEFAULT_IMPACT_COMMITS) -> dict:
    """Files the impact tool should inspect when the caller does not pass paths.

    Prefers the working tree. When the tree is clean, unions files from the
    recent commit window so a tip-only schema change does not hide an earlier
    logic defect in another file.
    """
    import git

    bounded = min(max(int(commit_limit), 1), _MAX_COMMITS)
    try:
        repo = git.Repo(repo_root())
    except git.InvalidGitRepositoryError:
        return {"source": "unavailable", "files": []}

    staged = _name_only(repo, cached=True)
    unstaged = _name_only(repo, cached=False)
    untracked = [path.replace("\\", "/") for path in repo.untracked_files]
    files = sorted(set(staged) | set(unstaged) | set(untracked))
    if files:
        return {"source": "working_tree", "files": files}

    head_files: set[str] = set()
    for commit in repo.iter_commits(max_count=bounded):
        head_files.update(path.replace("\\", "/") for path in commit.stats.files)
    return {"source": "recent_commits", "files": sorted(head_files)}


def register(mcp: FastMCP) -> None:
    mcp.tool(get_recent_changes)


def _name_only(repo, *, cached: bool) -> list[str]:
    args = ["--name-only", "--cached"] if cached else ["--name-only"]
    text = repo.git.diff(*args)
    return sorted(line.strip().replace("\\", "/") for line in text.splitlines() if line.strip())
