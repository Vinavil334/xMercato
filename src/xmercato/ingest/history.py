"""Historical match table: results and odds (football-data.co.uk) joined with xG (Understat).

Within a season every (home, away) pair is played once, so the two sources are joined on
season, home and away after mapping team names; dates and scores are then used as a check.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

import pandas as pd

from xmercato.ingest import football_data, teams, understat

COLUMNS = [
    "season", "date", "home", "away", "home_goals", "away_goals", "home_xg", "away_xg",
    "odds_home", "odds_draw", "odds_away", "odds_source",
]  # fmt: skip


def combine(results: pd.DataFrame, xg: pd.DataFrame, season: int) -> pd.DataFrame:
    """Join one season. Raises if the sources disagree on which matches were played."""
    mapping = teams.map_names(
        set(xg["home"]) | set(xg["away"]), set(results["home"]) | set(results["away"])
    )
    xg = xg.assign(home=xg["home"].map(mapping), away=xg["away"].map(mapping))
    merged = results.merge(
        xg[["home", "away", "date", "home_goals", "away_goals", "home_xg", "away_xg"]],
        on=["home", "away"],
        how="left",
        suffixes=("", "_us"),
        validate="one_to_one",
    )
    found = merged["home_xg"].notna()
    if (~found).sum() > 2:  # a couple of abandoned or awarded matches are tolerated
        missing = merged.loc[~found, ["date", "home", "away"]]
        raise ValueError(f"{season}: {len(missing)} matches without xG, e.g.\n{missing.head()}")
    days = (merged["date"] - merged["date_us"]).abs().dt.days
    late = found & (days > 3)
    if late.any():
        raise ValueError(f"{season}: dates differ by more than 3 days:\n{merged[late].head()}")
    # Scores can differ for matches awarded at the table (3-0): keep the official one.
    merged = merged.assign(season=season)
    return merged[COLUMNS]


def build(
    seasons: Iterable[int],
    load_results: Callable[[int], pd.DataFrame] | None = None,
    load_xg: Callable[[int], pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Combined table for several seasons; loaders can be replaced, e.g. in tests."""
    load_results = load_results or (
        lambda s: football_data.load_matches(football_data.serie_a_url(s))
    )
    load_xg = load_xg or understat.load_season
    frames = [combine(load_results(s), load_xg(s), s) for s in seasons]
    return pd.concat(frames, ignore_index=True).sort_values(["date", "home"], kind="stable")


def read(path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path} is not a history table, missing {missing}")
    return df
