"""Git versioning, branching, rollback, and commit summarizer for desired-state."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = ["StateRepository", "generate_deterministic_commit_msg"]

try:
    import git
    from git import Repo
    _HAS_GITPY = True
except ImportError:  # pragma: no cover
    git = None  # type: ignore
    Repo = None  # type: ignore
    _HAS_GITPY = False


def _require_gitpy() -> None:
    if not _HAS_GITPY:
        raise RuntimeError("GitPython is not installed. Run: pip install gitpython")


def generate_deterministic_commit_msg(diff: Dict[str, Any]) -> str:
    """Generate a Conventional Commit message from an executor diff.

    Produces clauses like:
      feat(packages): add VisualStudioCode, 7zip + 1 more
      feat(packages): remove 7zip
      chore(system): configure dark_mode, hide_taskbar_search
    joined with '; '. Falls back to 'chore: update system state'.
    """
    if not isinstance(diff, dict):
        return "chore: update system state"

    parts: List[str] = []

    def _format_segments(raw_items: List[str], max_shown: int = 3) -> str:
        segments = [str(item).split(".")[-1] for item in raw_items if item]
        if not segments:
            return ""
        if len(segments) <= max_shown:
            return ", ".join(segments)
        shown = ", ".join(segments[:max_shown])
        extra = len(segments) - max_shown
        return f"{shown} + {extra} more"

    # 1. Package additions (winget + scoop)
    adds = list(diff.get("winget_add") or []) + list(diff.get("scoop_add") or [])
    if adds:
        formatted_adds = _format_segments(adds)
        if formatted_adds:
            parts.append(f"feat(packages): add {formatted_adds}")

    # 2. Package removals (winget + scoop)
    removes = list(diff.get("winget_remove") or []) + list(diff.get("scoop_remove") or [])
    if removes:
        formatted_removes = _format_segments(removes)
        if formatted_removes:
            parts.append(f"feat(packages): remove {formatted_removes}")

    # 3. System tweaks (up to 2 keys)
    system_tweaks = diff.get("system_tweaks") or {}
    if isinstance(system_tweaks, dict) and system_tweaks:
        keys = list(system_tweaks.keys())[:2]
        if keys:
            parts.append(f"chore(system): configure {', '.join(str(k) for k in keys)}")

    if parts:
        return "; ".join(parts)
    return "chore: update system state"


class StateRepository:
    """Wraps ~/.keraunos (or any dir) as a git repo tracking state.yaml."""

    def __init__(self, repo_path: Path | str = Path.home() / ".keraunos"):
        _require_gitpy()
        self.repo_path = Path(repo_path)
        self.repo_path.mkdir(parents=True, exist_ok=True)
        git_dir = self.repo_path / ".git"
        assert Repo is not None
        if not git_dir.exists():
            self.repo: Repo = Repo.init(self.repo_path)
            # Local defaults so commits work without global git config.
            with self.repo.config_writer() as cw:
                cw.set_value("user", "name", "keraunos").release()
            with self.repo.config_writer() as cw:
                try:
                    cw.get_value("user", "email")
                except Exception:
                    cw.set_value("user", "email", "keraunos@localhost").release()
        else:
            self.repo = Repo(self.repo_path)

    # -- commits -----------------------------------------------------------------
    def commit_evolution(self, message: str, *, files: Optional[List[str]] = None) -> str:
        message = (message or "").strip() or f"state update {datetime.now(timezone.utc).isoformat()}"
        if files:
            self.repo.index.add(files)
        else:
            self.repo.git.add(A=True)
        if not self.repo.is_dirty(untracked_files=True) and self.repo.head.is_valid():
            # Nothing to commit — return current HEAD.
            return self.repo.head.commit.hexsha
        commit = self.repo.index.commit(message)
        return commit.hexsha

    def summarize_diff(self, a_sha: Optional[str] = None) -> str:
        """One-line human summary of staged/working diff (for commit messages / UI)."""
        try:
            diff = self.repo.git.diff(a_sha) if a_sha else self.repo.git.diff()
        except Exception:
            return "state changed"
        lines = [ln for ln in diff.splitlines() if ln.startswith(("+", "-")) and not ln.startswith(("+++", "---"))]
        adds = sum(1 for ln in lines if ln.startswith("+"))
        dels = sum(1 for ln in lines if ln.startswith("-"))
        return f"{adds} addition(s), {dels} deletion(s)"

    # -- history -----------------------------------------------------------------
    def log(self, limit: int = 20) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        try:
            for c in self.repo.iter_commits(max_count=limit):
                out.append({
                    "sha": c.hexsha,
                    "short": c.hexsha[:8],
                    "message": (c.message or "").strip().splitlines()[0][:120] if c.message else "",
                    "author": str(c.author) if c.author else "",
                    "date": c.committed_datetime.isoformat() if c.committed_datetime else "",
                })
        except Exception:
            pass
        return out

    def show_file_at(self, commit_sha: str, filename: str = "state.yaml") -> str:
        try:
            return self.repo.git.show(f"{commit_sha}:./{filename}")
        except Exception as exc:
            raise RuntimeError(f"Cannot read {filename} at {commit_sha}: {exc}") from exc

    # -- rollback / branches -------------------------------------------------------
    def rollback_to_commit(self, commit_sha: str, *, filename: str = "state.yaml",
                           commit_after: bool = True) -> str:
        """Checkout <file> from <commit>, optionally committing the restoration."""
        try:
            self.repo.git.checkout(commit_sha, "--", filename)
        except Exception as exc:
            raise RuntimeError(f"Rollback failed — unknown commit or file: {exc}") from exc
        if commit_after:
            return self.commit_evolution(f"rollback {filename} to {commit_sha[:8]}")
        return commit_sha

    def create_branch(self, name: str) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Branch name must be non-empty")
        self.repo.git.checkout("-b", name)

    def checkout(self, ref: str) -> None:
        self.repo.git.checkout(ref)

    def current_branch(self) -> str:
        try:
            return self.repo.active_branch.name
        except Exception:
            return "(detached)"

    # -- remotes -------------------------------------------------------------------
    def list_remotes(self) -> Dict[str, str]:
        return {r.name: next(iter(r.urls), "") for r in self.repo.remotes}

    def get_remote_url(self, name: str = "origin") -> Optional[str]:
        for r in self.repo.remotes:
            if r.name == name:
                return next(iter(r.urls), "")
        return None

    def set_remote(self, remote_url: str, name: str = "origin") -> str:
        """Create or replace remote ``name`` -> ``remote_url``. Returns the URL."""
        remote_url = (remote_url or "").strip()
        if not remote_url:
            raise ValueError("Remote URL must be non-empty")
        name = (name or "origin").strip() or "origin"
        if name in [r.name for r in self.repo.remotes]:
            self.repo.delete_remote(name)
        self.repo.create_remote(name, remote_url)
        return remote_url

    def _require_remote(self, remote_name: str):
        for r in self.repo.remotes:
            if r.name == remote_name:
                return r
        raise ValueError(
            f"Remote '{remote_name}' not configured. "
            f"Run: python keraunos.py remote set <url> [--name {remote_name}]"
        )

    def _active_branch_name(self) -> str:
        try:
            return self.repo.active_branch.name
        except Exception as exc:
            raise RuntimeError(
                "Cannot determine current branch (detached HEAD or empty repo). "
                "Commit state first, then push."
            ) from exc

    def push(self, remote_name: str = "origin", branch: str = "main",
             *, set_upstream: bool = False) -> bool:
        """Push current branch to ``remote_name:branch``. Returns True on success."""
        remote = self._require_remote(remote_name)
        current = self._active_branch_name()
        try:
            push_info = remote.push(f"{current}:{branch}")
            for info in push_info or []:
                flags = getattr(info, "flags", 0)
                # GitPython sets ERROR flag bit on failure.
                if flags & getattr(info, "ERROR", 0):
                    raise RuntimeError(f"Push rejected: {getattr(info, 'summary', info)}")
        except ValueError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"Push to '{remote_name}/{branch}' failed: {exc}. "
                "Check the remote URL, credentials, and network access."
            ) from exc
        if set_upstream:
            try:
                self.repo.git.branch("--set-upstream-to", f"{remote_name}/{branch}", current)
            except Exception:
                pass
        return True

    def pull(self, remote_name: str = "origin", branch: str = "main") -> bool:
        """Pull ``branch`` from ``remote_name`` into the current branch."""
        remote = self._require_remote(remote_name)
        try:
            remote.pull(branch)
        except Exception as exc:
            raise RuntimeError(
                f"Pull from '{remote_name}/{branch}' failed: {exc}. "
                "Resolve conflicts manually, then retry."
            ) from exc
        return True

    def fetch(self, remote_name: str = "origin") -> bool:
        remote = self._require_remote(remote_name)
        try:
            remote.fetch()
        except Exception as exc:
            raise RuntimeError(f"Fetch from '{remote_name}' failed: {exc}") from exc
        return True

    def get_history(self, limit: int = 15) -> List[Dict[str, str]]:
        """Compact history (spec-compatible keys) for UI/CLI display."""
        out: List[Dict[str, str]] = []
        try:
            for c in list(self.repo.iter_commits(max_count=limit)):
                out.append({
                    "sha": c.hexsha[:7],
                    "full_sha": c.hexsha,
                    "message": (c.message or "").strip().splitlines()[0][:200] if c.message else "",
                    "date": c.committed_datetime.strftime("%Y-%m-%d %H:%M:%S")
                    if c.committed_datetime else "",
                })
        except Exception:
            pass
        return out

    @classmethod
    def clone(cls, remote_url: str, dest: Path | str,
              *, branch: Optional[str] = None) -> "StateRepository":
        """Clone ``remote_url`` into ``dest`` and return a bound repository."""
        _require_gitpy()
        assert Repo is not None
        dest_p = Path(dest)
        if dest_p.exists() and any(dest_p.iterdir()):
            raise RuntimeError(f"Clone destination is not empty: {dest_p}")
        try:
            if branch:
                Repo.clone_from(remote_url, dest_p, branch=branch)
            else:
                Repo.clone_from(remote_url, dest_p)
        except Exception as exc:
            raise RuntimeError(f"Clone from '{remote_url}' failed: {exc}") from exc
        return cls(dest_p)
