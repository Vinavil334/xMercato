"""Historical match table: results and odds (football-data.co.uk) joined with xG (Understat).

Within a season every (home, away) pair is played once, so the two sources are joined on
season, home and away after mapping team names; dates are then used as a check. xG is
available only for the seasons in the Understat archive (see ``ingest.understat``).
"""

from __future__ import annotations

import warnings
from collections.abc import Callable, Iterable

import pandas as pd

from xmercato.ingest import football_data, teams

COLUMNS = [
    "season", "date", "home", "away", "home_goals", "away_goals", "home_xg", "away_xg",
    "odds_home", "odds_draw", "odds_away", "odds_source",
]  # fmt: skip


def combine(results: pd.DataFrame, xg: pd.DataFrame | None, season: int) -> pd.DataFrame:
    """Join one season. ``xg`` may be empty or cover only part of the season.

    Raises if a club cannot be mapped or if many matches are dated differently by the
    two sources; a few (suspended matches completed later) only raise a warning.
    """
    merged = results.assign(season=season)
    if xg is None or xg.empty:
        return merged.assign(home_xg=float("nan"), away_xg=float("nan"))[COLUMNS]
    mapping = teams.map_names(
        set(xg["home"]) | set(xg["away"]), set(results["home"]) | set(results["away"])
    )
    xg = xg.assign(home=xg["home"].map(mapping), away=xg["away"].map(mapping))
    merged = merged.merge(
        xg[["home", "away", "date", "home_xg", "away_xg"]],
        on=["home", "away"],
        how="left",
        suffixes=("", "_xg"),
        validate="one_to_one",
    )
    found = merged["home_xg"].notna()
    days = (merged["date"] - merged["date_xg"]).abs().dt.days
    late = found & (days > 3)
    # A suspended match completed later (e.g. Udinese-Roma, April 2024) is dated differently
    # by the two sources. A few cases are expected; many mean a wrong join.
    if late.sum() > 3:
        raise ValueError(f"{season}: dates differ by more than 3 days:\n{merged[late].head()}")
    for row in merged[late].itertuples():
        warnings.warn(
            f"{season} {row.home}-{row.away}: dated {row.date:%Y-%m-%d} in the results, "
            f"{row.date_xg:%Y-%m-%d} in the xG source",
            stacklevel=2,
        )
    return merged[COLUMNS]


def build(
    seasons: Iterable[int],
    load_results: Callable[[int], pd.DataFrame] | None = None,
    xg: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Combined table for several seasons.

    ``load_results`` defaults to the football-data.co.uk file of each season. ``xg`` is a
    match-level xG table for any number of seasons (see :func:`understat.match_xg`).
    """
    load_results = load_results or (
        lambda s: football_data.load_matches(football_data.serie_a_url(s))
    )
    frames = []
    for season in seasons:
        season_xg = None if xg is None else xg[xg["season"] == season]
        frames.append(combine(load_results(season), season_xg, season))
    return pd.concat(frames, ignore_index=True).sort_values(["date", "home"], kind="stable")


def read(path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path} is not a history table, missing {missing}")
    return df
