"""Match-level xG from understat.com.

Understat serves a season's matches from ``/getLeagueData/<league>/<season>`` (JSON, needs
an ``X-Requested-With`` header); older versions of the site embedded the same list in the
league page as ``var datesData = JSON.parse('...')``. Both are supported.

There is no official API and no licence: keep requests few and slow, cache the results,
and credit understat.com wherever the data is shown.
"""

from __future__ import annotations

import gzip
import json
import re
import time
import urllib.request

import pandas as pd

BASE_URL = "https://understat.com"
SERIE_A = "Serie_A"
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) xMercato/0.1 (+https://github.com/Vinavil334/xMercato)"
)


def _get(url: str, headers: dict[str, str] | None = None, timeout: float = 30) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (fixed host)
        body = response.read()
        if response.headers.get("Content-Encoding") == "gzip" or body[:2] == b"\x1f\x8b":
            body = gzip.decompress(body)
    return body.decode("utf-8")


def parse_events(events: list[dict]) -> pd.DataFrame:
    """Played matches from Understat's list of events, one row per match."""
    rows = [
        {
            "date": pd.Timestamp(e["datetime"]).normalize(),
            "home": e["h"]["title"],
            "away": e["a"]["title"],
            "home_goals": int(e["goals"]["h"]),
            "away_goals": int(e["goals"]["a"]),
            "home_xg": float(e["xG"]["h"]),
            "away_xg": float(e["xG"]["a"]),
            "understat_id": int(e["id"]),
        }
        for e in events
        if e.get("isResult") in (True, "true")
    ]
    columns = ["date", "home", "away", "home_goals", "away_goals", "home_xg", "away_xg"]
    df = pd.DataFrame(rows, columns=[*columns, "understat_id"])
    return df.sort_values(["date", "understat_id"], kind="stable").reset_index(drop=True)


def parse_league_page(html: str) -> list[dict]:
    """Events embedded in an old-style league page (``datesData``)."""
    match = re.search(r"var\s+datesData\s*=\s*JSON\.parse\('(.*?)'\)", html, re.DOTALL)
    if not match:
        raise ValueError("datesData not found in the page")
    return json.loads(match.group(1).encode("utf-8").decode("unicode_escape"))


def load_season(season_start: int, league: str = SERIE_A) -> pd.DataFrame:
    """Played matches of one season (``season_start=2025`` for 2025/26), with xG."""
    page = f"{BASE_URL}/league/{league}/{season_start}"
    try:
        payload = json.loads(
            _get(
                f"{BASE_URL}/getLeagueData/{league}/{season_start}",
                {"X-Requested-With": "XMLHttpRequest", "Referer": page},
            )
        )
        events = payload["dates"]
    except Exception:  # endpoint changed or refused: fall back to the page
        events = parse_league_page(_get(page))
    return parse_events(events).assign(season=season_start)


def load_seasons(seasons: list[int], league: str = SERIE_A, pause: float = 2.0) -> pd.DataFrame:
    frames = []
    for k, season in enumerate(seasons):
        if k:
            time.sleep(pause)  # be gentle with a free site
        frames.append(load_season(season, league))
    return pd.concat(frames, ignore_index=True)
