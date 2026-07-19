"""Loads PROJECTX_USERNAME / PROJECTX_API_KEY from .env (gitignored) or the environment.

Uses `python-dotenv` (already a project dependency -- see requirements.txt
and Analysis/scripts/fetch_nq_ohlcv_databento.py's identical
`load_dotenv(ROOT / ".env")` pattern, reused here rather than reinvented).

Credentials must NEVER appear in logs/journals: this module returns them as
a `ProjectXCredentials` dataclass and callers (src/live/runner.py) pass them
straight into `ProjectXClient` -- nowhere in this package does a credential
get formatted into a log/event-journal string. `ProjectXCredentials.__repr__`
is overridden to redact the api_key so an accidental `print(creds)` or
journaled dataclass repr never leaks it.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


class MissingCredentialsError(RuntimeError):
    """Raised when PROJECTX_USERNAME or PROJECTX_API_KEY is not set."""


@dataclass(frozen=True)
class ProjectXCredentials:
    username: str
    api_key: str

    def __repr__(self) -> str:  # pragma: no cover -- trivial, but load-bearing for the no-leak guarantee
        return f"ProjectXCredentials(username={self.username!r}, api_key='***redacted***')"


def load_projectx_credentials(*, env_path: Path | None = None) -> ProjectXCredentials:
    """Loads .env (if present) then reads PROJECTX_USERNAME/PROJECTX_API_KEY from os.environ.

    Raises `MissingCredentialsError` (naming BOTH missing var names if both
    are absent) rather than returning a partially-empty credentials object
    -- a live trading client must never be constructed with a blank
    username or key.
    """
    load_dotenv(env_path or (ROOT / ".env"))
    username = os.environ.get("PROJECTX_USERNAME", "").strip()
    api_key = os.environ.get("PROJECTX_API_KEY", "").strip()
    missing = [name for name, value in (("PROJECTX_USERNAME", username), ("PROJECTX_API_KEY", api_key)) if not value]
    if missing:
        raise MissingCredentialsError(
            f"missing required .env variable(s): {', '.join(missing)}. See RUNBOOK_LIVE.md step 3 "
            "(write .env) for the exact keys to set."
        )
    return ProjectXCredentials(username=username, api_key=api_key)
