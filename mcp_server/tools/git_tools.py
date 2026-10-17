"""Read recent Git commits and diffs. This tool does not modify the repository."""

from __future__ import annotations

from fastmcp import FastMCP

from mcp_server.dependencies import repo_root, truncate

_MAX_COMMITS = 20


def get_recent_changes(limit: int = 5) -> dict:
    """Return recent commits plus the latest commit diff and any uncommitted diff.

    `limit` is capped at 20. Patch text is truncated so a tool response stays
    small enough for the agent to read.
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

    latest_diff = ""
    if commits:
        latest_diff = truncate(repo.git.show("--format=", "--patch", commits[0]["sha"]))

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
        "latest_diff": latest_diff,
        "staged_diff": staged_diff,
        "working_tree_diff": working_tree_diff,
    }


def changed_files_for_impact() -> dict:
    """Files the impact tool should inspect when the caller does not pass paths."""
    import git

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

    head_files = sorted(repo.head.commit.stats.files)
    return {"source": "latest_commit", "files": head_files}


def register(mcp: FastMCP) -> None:
    mcp.tool(get_recent_changes)


def _name_only(repo, *, cached: bool) -> list[str]:
    args = ["--name-only", "--cached"] if cached else ["--name-only"]
    text = repo.git.diff(*args)
    return sorted(line.strip().replace("\\", "/") for line in text.splitlines() if line.strip())
