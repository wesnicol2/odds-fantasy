"""What commit is actually running.

Delivery here is pull-based: CI pushes a tag to GHCR and Watchtower on the home
server recreates the container whenever the digest moves. Nothing in that loop
tells you *which* commit ended up running, and "did my change actually deploy?"
is otherwise answered by guessing at timestamps. So the commit is baked into
the image at build time and surfaced by `/health`, which the UI renders in a
footer.

Three sources, in order of trust:

1. **`APP_COMMIT`** — set by the Dockerfile from a build arg CI fills in with
   `github.sha`. This is the real answer for anything deployed, and the only
   one available inside the image: `.dockerignore` excludes `.git`, so a
   container has no repository to interrogate.
2. **`git rev-parse`** — for `python -m oddsfantasy.api` in a checkout. It also
   reports whether the tree is dirty, because a footer claiming a commit whose
   code you have since edited is worse than one admitting it doesn't know.
3. **Unknown** — surfaced as exactly that. An unlabelled build should look
   unlabelled rather than blank.
"""

from __future__ import annotations

import functools
import os
import subprocess
from pathlib import Path

UNKNOWN = "unknown"
SHORT_LENGTH = 7

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Seconds to wait on git before giving up. Running from a checkout is a
# developer convenience; it must never hold up a health check.
_GIT_TIMEOUT = 2.0


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _from_git() -> dict | None:
    if not (_REPO_ROOT / ".git").exists():
        return None
    commit = _git("rev-parse", "HEAD")
    if not commit:
        return None
    dirty = bool(_git("status", "--porcelain"))
    return {
        "commit": commit,
        "dirty": dirty,
        "source": "git",
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
    }


def _from_env() -> dict | None:
    commit = (os.getenv("APP_COMMIT") or "").strip()
    if not commit or commit == UNKNOWN:
        return None
    return {
        "commit": commit,
        "dirty": False,
        "source": "image",
        "branch": (os.getenv("APP_BRANCH") or "").strip() or None,
    }


@functools.cache
def build_info() -> dict:
    """Identify the running build. Cached: it cannot change under a process."""
    info = (
        _from_env()
        or _from_git()
        or {
            "commit": UNKNOWN,
            "dirty": False,
            "source": UNKNOWN,
            "branch": None,
        }
    )
    commit = info["commit"]
    info["commit_short"] = commit[:SHORT_LENGTH] if commit != UNKNOWN else UNKNOWN
    info["image_tag"] = (os.getenv("APP_IMAGE_TAG") or "").strip() or None
    info["built_at"] = (os.getenv("APP_BUILT_AT") or "").strip() or None
    return info
