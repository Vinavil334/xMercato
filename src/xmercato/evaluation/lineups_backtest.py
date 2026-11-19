"""How much a weaker starting eleven is worth in goals, measured on bookmaker odds.

1. For every Serie A game since 2019, the value of each side's starting eleven against its
   usual one (median of its previous ten league games): a log change, ``delta``.
2. The goals each side was expected to score: by our results-only model (walk-forward, as
   in :mod:`xmercato.evaluation.backtest`) and by the bookmakers' closing odds, which
   already know the line-ups (the two Poisson means that reproduce the 1X2 odds).
3. Regression of log(bookmaker / model) on the side's own delta and the opponent's.

Goals themselves are too noisy for this (see docs/STUDIO.md); the odds are not. The last
step checks whether adjusting the model by the actual line-ups would have improved its
predictions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from xmercato.evaluation import backtest
from xmercato.ingest import teams as team_names
from xmercato.models import forecast, poisson
from xmercato.models.lineups import Effect


def deltas(elevens: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    """Log value of each eleven against the median of the club's previous ``window`` games."""
    e = elevens.sort_values(["date", "game_id"]).copy()
    e = e[e["starters"] >= 10]
    e["log_value"] = np.log((e["value_attack"] + e["value_defence"]).clip(lower=1))
    usual = e.groupby(["club_id", "season"])["log_value"].transform(
        lambda s: s.shift(1).rolling(window, min_periods=3).median()
    )
    return e.assign(delta=e["log_value"] - usual).dropna(subset=["delta"])


def implied_rates(p_home: np.ndarray, p_away: np.ndarray) -> np.ndarray:
    """Poisson means (home, away) whose home-win and away-win chances match the odds."""
    out = np.empty((len(p_home), 2))
    for k, (ph, pa) in enumerate(zip(p_home, p_away, strict=True)):

        def gap(x: np.ndarray, ph: float = ph, pa: float = pa) -> list[float]:
            p = poisson.outcome_probabilities(np.exp(x[:1]), np.exp(x[1:]))[0]
            return [p[0] - ph, p[2] - pa]

        out[k] = np.exp(least_squares(gap, [0.3, 0.1]).x)
    return out


def matched_games(
    history: pd.DataFrame,
    elevens: pd.DataFrame,
    club_names: dict[int, str],
    seasons: range,
    config: forecast.ModelConfig = forecast.GOALS,
) -> pd.DataFrame:
    """Model and bookmaker expected goals, with both sides' eleven deltas, game by game."""
    preds = pd.concat([backtest.predict_season(history, s, config) for s in seasons])
    preds = preds.dropna(subset=["odds_home", "odds_draw", "odds_away"])
    book = backtest.bookmaker_probabilities(preds)
    rates = implied_rates(book["p_home"].to_numpy(), book["p_away"].to_numpy())
    preds = preds.assign(book_h=rates[:, 0], book_a=rates[:, 1])

    d = deltas(elevens)
    named = []
    for season, rows in d.groupby("season"):
        names = {c: club_names.get(c, str(c)) for c in set(rows["club_id"])}
        mapping = team_names.map_names(
            set(names.values()), set(history.loc[history["season"] == season, "home"])
        )
        named.append(rows.assign(team=rows["club_id"].map(names).map(mapping)))
    d = pd.concat(named)
    d["date"] = pd.to_datetime(d["date"])
    home = d[d["home"] == 1][["date", "team", "delta"]].rename(
        columns={"team": "home", "delta": "delta_h"}
    )
    away = d[d["home"] == 0][["date", "team", "delta"]].rename(
        columns={"team": "away", "delta": "delta_a"}
    )
    return preds.merge(home, on=["date", "home"]).merge(away, on=["date", "away"])


def estimate(games: pd.DataFrame) -> tuple[Effect, tuple[float, float]]:
    """Least squares on both sides of every game; returns the effect and its 95% margins."""
    y = np.concatenate(
        [np.log(games["book_h"] / games["lam_h"]), np.log(games["book_a"] / games["lam_a"])]
    )
    x = np.column_stack(
        [
            np.concatenate([games["delta_h"], games["delta_a"]]),
            np.concatenate([games["delta_a"], games["delta_h"]]),
            np.ones(2 * len(games)),
        ]
    )
    b, *_ = np.linalg.lstsq(x, y, rcond=None)
    residual = y - x @ b
    se = np.sqrt(np.diag(residual.var() * np.linalg.inv(x.T @ x)))
    return Effect(own=float(b[0]), opponent=float(b[1])), (1.96 * se[0], 1.96 * se[1])


def score_with(games: pd.DataFrame, effect: Effect) -> pd.Series:
    """Mean log loss and RPS of the model adjusted by the actual elevens."""
    lam_h = games["lam_h"] * np.exp(
        effect.own * games["delta_h"] + effect.opponent * games["delta_a"]
    )
    lam_a = games["lam_a"] * np.exp(
        effect.own * games["delta_a"] + effect.opponent * games["delta_h"]
    )
    p = poisson.outcome_probabilities(lam_h.to_numpy(), lam_a.to_numpy())
    scored = backtest.score(games.assign(p_home=p[:, 0], p_draw=p[:, 1], p_away=p[:, 2]))
    return scored[["log_loss", "rps"]].mean()
