"""Walk-forward backtest of the team-strength model.

Every week of a season the model is fitted on the matches played *before* that week only,
and predicts the week's matches. Predictions are scored against the results and against
the bookmakers' closing odds, the strongest public benchmark.

A second check simulates the rest of the season at a few points (before the first
matchday, after 10, 19 and 28 rounds) and compares expected points with final points.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from xmercato.models import poisson
from xmercato.models.forecast import BASELINE, GOALS, XG_MIX, ModelConfig, fit_as_of
from xmercato.sim import season as season_sim


def _rates(strengths: poisson.TeamStrengths, matches: pd.DataFrame) -> tuple[np.ndarray, ...]:
    index = {t: k for k, t in enumerate(strengths.teams)}
    h = matches["home"].map(index).to_numpy()
    a = matches["away"].map(index).to_numpy()
    s = strengths
    lam_h = np.exp(s.mu + s.home_adv + s.attack[h] - s.defence[a])
    lam_a = np.exp(s.mu + s.attack[a] - s.defence[h])
    return lam_h, lam_a


# ------------------------------------------------------------------------ predictions


def predict_season(history: pd.DataFrame, season: int, config: ModelConfig) -> pd.DataFrame:
    """1X2 probabilities for every match of ``season``, each from a fit on earlier matches."""
    matches = history[history["season"] == season].copy()
    teams = set(matches["home"]) | set(matches["away"])
    # Weeks run Tuesday to Monday, so a weekend round and its Monday games stay together.
    matches["week"] = matches["date"].dt.to_period("W-MON")
    out = []
    for _, week in matches.groupby("week", sort=True):
        strengths = fit_as_of(history, season, week["date"].min(), config, teams)
        lam_h, lam_a = _rates(strengths, week)
        probs = poisson.outcome_probabilities(lam_h, lam_a)
        out.append(week.assign(p_home=probs[:, 0], p_draw=probs[:, 1], p_away=probs[:, 2]))
    return pd.concat(out).drop(columns="week").assign(model=config.name)


def bookmaker_probabilities(matches: pd.DataFrame) -> pd.DataFrame:
    """Closing odds turned into probabilities (margin removed proportionally)."""
    inv = 1 / matches[["odds_home", "odds_draw", "odds_away"]].to_numpy(dtype=float)
    probs = inv / inv.sum(axis=1, keepdims=True)
    return matches.assign(
        p_home=probs[:, 0], p_draw=probs[:, 1], p_away=probs[:, 2], model="bookmaker"
    )


def score(predictions: pd.DataFrame) -> pd.DataFrame:
    """Per-match scores: log loss, ranked probability score and Brier score (lower is better)."""
    p = predictions[["p_home", "p_draw", "p_away"]].to_numpy(dtype=float)
    outcome = np.select(
        [
            predictions["home_goals"] > predictions["away_goals"],
            predictions["home_goals"] == predictions["away_goals"],
        ],
        [0, 1],
        2,
    )
    onehot = np.eye(3)[outcome]
    cum_p, cum_o = np.cumsum(p, axis=1)[:, :2], np.cumsum(onehot, axis=1)[:, :2]
    return predictions.assign(
        log_loss=-np.log(np.clip(p[np.arange(len(p)), outcome], 1e-12, 1)),
        rps=((cum_p - cum_o) ** 2).sum(axis=1) / 2,
        brier=((p - onehot) ** 2).sum(axis=1),
    )


def summary(scored: pd.DataFrame, by: list[str] | None = None) -> pd.DataFrame:
    by = by or ["model"]
    return (
        scored.groupby(by)[["log_loss", "rps", "brier"]]
        .mean()
        .assign(partite=scored.groupby(by).size())
        .round(4)
    )


# ------------------------------------------------------------------------- final table


def final_points(matches: pd.DataFrame) -> pd.Series:
    hg, ag = matches["home_goals"], matches["away_goals"]
    home = (3 * (hg > ag) + (hg == ag)).groupby(matches["home"]).sum()
    away = (3 * (ag > hg) + (hg == ag)).groupby(matches["away"]).sum()
    return home.add(away, fill_value=0).astype(int)


def table_errors(
    history: pd.DataFrame,
    season: int,
    config: ModelConfig,
    rounds: Iterable[int] = (0, 10, 19, 28),
    n_sims: int = 2000,
    seed: int = 0,
) -> pd.DataFrame:
    """Mean absolute error on final points, simulating the rest of the season at each round."""
    matches = history[history["season"] == season].sort_values("date", kind="stable")
    teams = sorted(set(matches["home"]))
    per_round = len(teams) // 2
    actual = final_points(matches)
    rows = []
    for r in rounds:
        played = matches.iloc[: r * per_round]
        cutoff = matches["date"].iloc[r * per_round] if r * per_round < len(matches) else None
        if cutoff is None:
            continue
        if r == 0 and config.history_seasons == 0:
            continue  # nothing to fit on before the first matchday
        strengths = fit_as_of(history, season, cutoff, config, teams)
        table = season_sim.simulate(strengths, played, n_sims=n_sims, seed=seed)
        err = (table["exp_points"] - actual.reindex(table.index)).abs()
        rows.append({"model": config.name, "season": season, "round": r, "mae": err.mean()})
    return pd.DataFrame(rows)


def naive_table_errors(
    history: pd.DataFrame, season: int, rounds: Iterable[int] = (10, 19, 28)
) -> pd.DataFrame:
    """Baseline: every team keeps its current points per game until the end."""
    matches = history[history["season"] == season].sort_values("date", kind="stable")
    teams = sorted(set(matches["home"]))
    per_round, total = len(teams) // 2, 2 * (len(teams) - 1)
    actual = final_points(matches)
    rows = []
    for r in rounds:
        played = matches.iloc[: r * per_round]
        if played.empty or r >= total:
            continue
        pts = final_points(played).reindex(teams, fill_value=0)
        games = pd.concat([played["home"], played["away"]]).value_counts().reindex(teams)
        projected = pts / games * total
        err = (projected - actual.reindex(teams)).abs()
        rows.append(
            {"model": "media punti attuale", "season": season, "round": r, "mae": err.mean()}
        )
    return pd.DataFrame(rows)


def run(
    history: pd.DataFrame,
    seasons: Iterable[int],
    configs: Iterable[ModelConfig] = (BASELINE, GOALS, XG_MIX),
    n_sims: int = 2000,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Match-level scores and final-table errors for each model, plus the benchmarks."""
    seasons, configs = list(seasons), list(configs)
    preds = [predict_season(history, s, c) for s in seasons for c in configs]
    preds.append(bookmaker_probabilities(history[history["season"].isin(seasons)]))
    scored = score(pd.concat(preds, ignore_index=True))
    tables = [table_errors(history, s, c, n_sims=n_sims) for s in seasons for c in configs]
    tables += [naive_table_errors(history, s) for s in seasons]
    return scored, pd.concat(tables, ignore_index=True)
