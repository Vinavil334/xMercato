"""Team strengths for a season, using earlier seasons too.

The plain fit in :mod:`xmercato.models.poisson` only sees what it is given. Here we decide
*what* it sees: how many past seasons, how much older matches count (time decay), goals or
expected goals (xG), and where newly promoted teams start. The settings in ``GOALS`` and
``XG_MIX`` were chosen by the backtest in :mod:`xmercato.evaluation.backtest`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace

import pandas as pd

from xmercato.models import poisson


@dataclass(frozen=True)
class ModelConfig:
    """How the model is fitted. The default is the original one: this season's goals only."""

    name: str = "solo stagione, gol"
    history_seasons: int = 0  # previous seasons used besides the current one
    half_life_days: float | None = None  # None: all matches weigh the same
    shrinkage: float = 2.0
    xg_share: float = 0.0  # 0: fit on goals, 1: on xG, in between: a mix
    promoted_prior: tuple[float, float] | None = None  # (attack, defence) of new teams

    def with_(self, **changes) -> ModelConfig:
        return replace(self, **changes)


# Chosen on the 2015-2019 seasons and tested on 2020-2025: see docs/STUDIO.md.
BASELINE = ModelConfig()
GOALS = ModelConfig(
    name="storico, gol",
    history_seasons=2,
    half_life_days=270,
    shrinkage=4.0,
    promoted_prior=(-0.45, -0.45),
)
XG_MIX = GOALS.with_(name="storico, gol + xG", xg_share=0.5)
CONFIGS = {"base": BASELINE, "gol": GOALS, "xg": XG_MIX}


def stack(seasons: Mapping[int, pd.DataFrame]) -> pd.DataFrame:
    """Results of several seasons in one table, with a ``season`` column (start year)."""
    frames = [df.assign(season=s) for s, df in sorted(seasons.items()) if df is not None]
    return pd.concat(frames, ignore_index=True)


def targets(matches: pd.DataFrame, xg_share: float) -> pd.DataFrame:
    """Fit targets: goals, xG or a mix; matches without xG fall back to goals."""
    if xg_share == 0 or "home_xg" not in matches:
        return matches.assign(t_home=matches["home_goals"], t_away=matches["away_goals"])
    hx = matches["home_xg"].fillna(matches["home_goals"])
    ax = matches["away_xg"].fillna(matches["away_goals"])
    return matches.assign(
        t_home=xg_share * hx + (1 - xg_share) * matches["home_goals"],
        t_away=xg_share * ax + (1 - xg_share) * matches["away_goals"],
    )


def promoted_teams(history: pd.DataFrame, season: int) -> set[str]:
    """Teams in ``season`` that did not play the previous season in this league."""
    before = set(history.loc[history["season"] == season - 1, "home"])
    if not before:
        return set()
    return set(history.loc[history["season"] == season, "home"]) - before


def fit_as_of(
    history: pd.DataFrame,
    season: int,
    as_of: pd.Timestamp,
    config: ModelConfig,
    teams: Iterable[str],
) -> poisson.TeamStrengths:
    """Strengths of ``teams`` from matches played before ``as_of``.

    Uses ``season`` and the ``config.history_seasons`` before it. Teams of earlier
    seasons enter the fit (their matches tell us about the others) but are left out
    of the result.
    """
    teams = sorted(set(teams))
    window = history[
        (history["date"] < as_of)
        & (history["season"] <= season)
        & (history["season"] >= season - config.history_seasons)
    ]
    window = targets(window, config.xg_share)
    everyone = sorted(set(teams) | set(window["home"]) | set(window["away"]))
    weights = (
        poisson.decay_weights(window["date"], as_of, config.half_life_days)
        if config.half_life_days
        else None
    )
    prior = None
    if config.promoted_prior is not None:
        new = promoted_teams(history, season) | (set(teams) - set(window["home"]))
        prior = dict.fromkeys(new & set(teams), config.promoted_prior) if window.size else None
    fitted = poisson.fit(
        window,
        teams=everyone,
        shrinkage=config.shrinkage,
        weights=weights,
        target=("t_home", "t_away"),
        prior=prior,
    )
    idx = [fitted.teams.index(t) for t in teams]
    return replace(
        fitted, teams=tuple(teams), attack=fitted.attack[idx], defence=fitted.defence[idx]
    )
