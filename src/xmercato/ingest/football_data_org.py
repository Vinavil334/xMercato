"""Scorers of the current season from the football-data.org API (free plan).

The free plan of football-data.org covers Serie A and lists, for every player who has
scored or assisted, his goals, assists, penalties and matches played. It needs a free
personal token (https://www.football-data.org/client/register), read here from the
``FOOTBALL_DATA_TOKEN`` environment variable. The terms ask for this credit wherever the
data is shown: "Football data provided by the Football-Data.org API".
"""

from __future__ import annotations

import json
import os
import urllib.request

import pandas as pd

API = "https://api.football-data.org/v4"
ATTRIBUTION = "Football data provided by the Football-Data.org API"
TOKEN_VARIABLE = "FOOTBALL_DATA_TOKEN"

COLUMNS = [
    "season",
    "player_id",
    "giocatore",
    "nascita",
    "nazionalita",
    "ruolo",
    "squadra",
    "partite",
    "gol",
    "assist",
    "rigori",
]


def token_from_env() -> str | None:
    return os.environ.get(TOKEN_VARIABLE) or None


def _get(path: str, token: str) -> dict:
    request = urllib.request.Request(
        f"{API}{path}", headers={"X-Auth-Token": token, "User-Agent": "xMercato"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 (fixed host)
        return json.load(response)


def parse_scorers(payload: dict) -> pd.DataFrame:
    """Flatten the ``/competitions/{code}/scorers`` answer into one row per player."""
    season = payload.get("season") or {}
    start = str(season.get("startDate", ""))[:4]
    rows = []
    for item in payload.get("scorers", []):
        player, team = item.get("player") or {}, item.get("team") or {}
        rows.append(
            {
                "season": int(start) if start.isdigit() else None,
                "player_id": player.get("id"),
                "giocatore": player.get("name"),
                "nascita": player.get("dateOfBirth"),
                "nazionalita": player.get("nationality"),
                "ruolo": player.get("section") or player.get("position"),
                "squadra": team.get("name"),
                "partite": item.get("playedMatches") or 0,
                "gol": item.get("goals") or 0,
                "assist": item.get("assists") or 0,
                "rigori": item.get("penalties") or 0,
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS)


def load_scorers(
    token: str, competition: str = "SA", season: int | None = None, limit: int = 500
) -> pd.DataFrame:
    """Everyone with a goal or an assist this season (one API call)."""
    query = f"?limit={limit}" + (f"&season={season}" if season else "")
    return parse_scorers(_get(f"/competitions/{competition}/scorers{query}", token))
