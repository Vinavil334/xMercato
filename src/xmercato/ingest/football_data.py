"""Match results in the football-data.co.uk CSV layout.

Works both with the original files (``https://www.football-data.co.uk/mmz4281/2526/I1.csv``,
dates as dd/mm/yyyy) and with the public-domain mirror in ``datasets/football-datasets``
on GitHub (ISO dates). Only the columns needed by the match model are kept.

``SAMPLE_SEASON`` is a complete season (Serie A 2025/26, from that mirror) shipped with
the package for tests, examples and as the app's offline fallback.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SERIE_A_URL = "https://www.football-data.co.uk/mmz4281/{season}/I1.csv"
SAMPLE_SEASON = Path(__file__).resolve().parents[1] / "samples" / "serie_a_2025_26.csv"

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


# Closing odds where available (Pinnacle, then market average), else opening odds.
_ODDS_PREFERENCE = [("PSCH", "PSCD", "PSCA"), ("AvgCH", "AvgCD", "AvgCA"), ("PSH", "PSD", "PSA"),
                    ("AvgH", "AvgD", "AvgA"), ("B365H", "B365D", "B365A")]  # fmt: skip


def _read_csv(source: str | Path) -> pd.DataFrame:
    try:
        return pd.read_csv(source, encoding="utf-8-sig")
    except UnicodeDecodeError:  # some old football-data.co.uk files are latin-1
        return pd.read_csv(source, encoding="latin-1")


def load_matches(source: str | Path) -> pd.DataFrame:
    """Played matches with bookmaker odds.

    Same columns as :func:`load_results`, plus ``odds_home``, ``odds_draw``, ``odds_away``
    (decimal odds, the most closing-like available for each match) and ``odds_source``.
    """
    raw = _read_csv(source)
    results = _clean(raw)
    odds = pd.DataFrame(
        index=raw.index, columns=["odds_home", "odds_draw", "odds_away"], dtype=float
    )
    origin = pd.Series("", index=raw.index)
    for cols in _ODDS_PREFERENCE:
        if not set(cols) <= set(raw.columns):
            continue
        values = raw[list(cols)].apply(pd.to_numeric, errors="coerce")
        fill = odds["odds_home"].isna() & values.notna().all(axis=1)
        odds.loc[fill] = values[fill].to_numpy()
        origin[fill] = cols[0].removesuffix("H")
    out = results.join(odds, how="left").assign(odds_source=origin.reindex(results.index))
    return out.sort_values("date", kind="stable").reset_index(drop=True)


def load_results(source: str | Path) -> pd.DataFrame:
    """Read played matches from a path or URL.

    Returns one row per played match with columns
    ``date, home, away, home_goals, away_goals``, sorted by date.
    Rows without a final score (postponed or future matches) are dropped.
    """
    return _clean(_read_csv(source)).sort_values("date", kind="stable").reset_index(drop=True)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Keep played matches and the result columns; the index of ``df`` is preserved."""
    missing = [c for c in _COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Not a football-data.co.uk results file, missing columns: {missing}")

    df = df[list(_COLUMNS)].rename(columns=_COLUMNS)
    df = df.dropna(subset=["home", "away", "home_goals", "away_goals"])
    df["date"] = _parse_dates(df["date"])
    df["home"] = df["home"].str.strip()
    df["away"] = df["away"].str.strip()
    df[["home_goals", "away_goals"]] = df[["home_goals", "away_goals"]].astype(int)
    return df
