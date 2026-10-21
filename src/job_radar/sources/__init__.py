"""Job sources. Every source uses an official public API; none scrapes HTML pages.

Each fetcher takes an httpx.Client and returns a list of Job. A failing source
logs a warning and returns [] so one broken board never stops the daily run.
"""

from __future__ import annotations

import html
import logging
import re
from collections.abc import Callable

import httpx

from job_radar.models import Job

log = logging.getLogger(__name__)

_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{3,}")


def html_to_text(raw: str | None) -> str:
    """Turns posting HTML (sometimes entity-escaped twice) into plain text."""
    if not raw:
        return ""
    text = html.unescape(html.unescape(raw))
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", text)
    text = _TAG.sub("", text)
    text = _SPACES.sub(" ", text)
    return _BLANK_LINES.sub("\n\n", text).strip()


def get_json(client: httpx.Client, url: str, **params) -> object | None:
    try:
        resp = client.get(url, params=params or None)
        resp.raise_for_status()
        return resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Skipping %s: %s", url, exc)
        return None


Fetcher = Callable[[httpx.Client, str, str], list[Job]]


def registry() -> dict[str, Fetcher]:
    from job_radar.sources import ashby, greenhouse, lever

    return {"greenhouse": greenhouse.fetch, "lever": lever.fetch, "ashby": ashby.fetch}
