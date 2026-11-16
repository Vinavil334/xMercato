"""Match results in the football-data.co.uk CSV layout.

Works both with the original files (``https://www.football-data.co.uk/mmz4281/2526/I1.csv``,
dates as dd/mm/yyyy) and with the public-domain mirror in ``datasets/football-datasets``
on GitHub (ISO dates). Only the columns needed by the match model are kept.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SERIE_A_URL = "https://www.football-data.co.uk/mmz4281/{season}/I1.csv"

_COLUMNS = {
    "Date": "date",
    "HomeTeam": "home",
    "AwayTeam": "away",
    "FTHG": "home_goals",
    "FTAG": "away_goals",
}


def serie_a_url(season_start: int) -> str:
    """URL of the Serie A file for the season starting in ``season_start`` (e.g. 2025)."""
    yy = season_start % 100
    return SERIE_A_URL.format(season=f"{yy:02d}{(yy + 1) % 100:02d}")


def _parse_dates(raw: pd.Series) -> pd.Series:
    raw = raw.astype(str).str.strip()
    if raw.str.match(r"^\d{4}-\d{2}-\d{2}$").all():
        return pd.to_datetime(raw, format="%Y-%m-%d")
    # football-data.co.uk uses dd/mm/yy in old files and dd/mm/yyyy in recent ones.
    return pd.to_datetime(raw, dayfirst=True, format="mixed")


def load_results(source: str | Path) -> pd.DataFrame:
    """Read played matches from a path or URL.

    Returns one row per played match with columns
    ``date, home, away, home_goals, away_goals``, sorted by date.
    Rows without a final score (postponed or future matches) are dropped.
    """
    df = pd.read_csv(source, encoding="utf-8-sig")
    missing = [c for c in _COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Not a football-data.co.uk results file, missing columns: {missing}")

    df = df[list(_COLUMNS)].rename(columns=_COLUMNS)
    df = df.dropna(subset=["home", "away", "home_goals", "away_goals"])
    df["date"] = _parse_dates(df["date"])
    df["home"] = df["home"].str.strip()
    df["away"] = df["away"].str.strip()
    df[["home_goals", "away_goals"]] = df[["home_goals", "away_goals"]].astype(int)
    return df.sort_values("date", kind="stable").reset_index(drop=True)
