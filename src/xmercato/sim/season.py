"""Monte Carlo simulation of the rest of a double round-robin season.

Known simplification: ties in the table are broken by goal difference, then goals
scored, then at random. Serie A actually uses head-to-head records, and a play-off
when the title or the last relegation place is tied on points.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from xmercato.models.poisson import TeamStrengths


def remaining_fixtures(results: pd.DataFrame, teams: list[str] | tuple[str, ...]) -> pd.DataFrame:
    """Fixtures still to play: every ordered (home, away) pair not found in ``results``."""
    played = set(zip(results["home"], results["away"], strict=True))
    todo = [(h, a) for h in teams for a in teams if h != a and (h, a) not in played]
    return pd.DataFrame(todo, columns=["home", "away"])


def simulate(
    strengths: TeamStrengths,
    results: pd.DataFrame,
    n_sims: int = 10_000,
    seed: int | None = None,
) -> pd.DataFrame:
    """Simulate the remaining fixtures ``n_sims`` times.

    Returns one row per team, sorted by expected points, with current points, expected
    final points and the probability of each final position (columns ``pos_1`` ... ``pos_N``).
    """
    teams = strengths.teams
    n = len(teams)
    index = {team: k for k, team in enumerate(teams)}
    rng = np.random.default_rng(seed)

    # Table so far.
    points = np.zeros(n)
    goals_for = np.zeros(n)
    goals_against = np.zeros(n)
    h = results["home"].map(index).to_numpy()
    a = results["away"].map(index).to_numpy()
    gh = results["home_goals"].to_numpy()
    ga = results["away_goals"].to_numpy()
    np.add.at(points, h, 3 * (gh > ga) + (gh == ga))
    np.add.at(points, a, 3 * (ga > gh) + (gh == ga))
    np.add.at(goals_for, h, gh)
    np.add.at(goals_for, a, ga)
    np.add.at(goals_against, h, ga)
    np.add.at(goals_against, a, gh)

    # Remaining fixtures, simulated all at once: arrays are (n_sims, n_fixtures).
    todo = remaining_fixtures(results, teams)
    fh = todo["home"].map(index).to_numpy(dtype=int)
    fa = todo["away"].map(index).to_numpy(dtype=int)
    lam_h = np.exp(strengths.mu + strengths.home_adv + strengths.attack[fh] - strengths.defence[fa])
    lam_a = np.exp(strengths.mu + strengths.attack[fa] - strengths.defence[fh])
    sim_h = rng.poisson(lam_h, size=(n_sims, len(todo)))
    sim_a = rng.poisson(lam_a, size=(n_sims, len(todo)))

    # Fixture-to-team incidence matrices turn per-fixture outcomes into per-team totals.
    home_of = np.zeros((len(todo), n))
    away_of = np.zeros((len(todo), n))
    home_of[np.arange(len(todo)), fh] = 1
    away_of[np.arange(len(todo)), fa] = 1

    draw = sim_h == sim_a
    final_points = (
        points + (3 * (sim_h > sim_a) + draw) @ home_of + (3 * (sim_a > sim_h) + draw) @ away_of
    )
    final_gf = goals_for + sim_h @ home_of + sim_a @ away_of
    final_ga = goals_against + sim_a @ home_of + sim_h @ away_of

    # Rank: points, then goal difference, then goals scored, then a random draw.
    key = (
        final_points * 1e7
        + (final_gf - final_ga + 500) * 1e4
        + final_gf * 10
        + rng.random((n_sims, n))
    )
    order = np.argsort(-key, axis=1)
    position = np.empty_like(order)
    position[np.arange(n_sims)[:, None], order] = np.arange(n)

    out = pd.DataFrame(
        {
            "played": np.bincount(h, minlength=n) + np.bincount(a, minlength=n),
            "points": points.astype(int),
            "exp_points": final_points.mean(axis=0),
        },
        index=pd.Index(teams, name="team"),
    )
    probs = pd.DataFrame(
        {f"pos_{p + 1}": (position == p).mean(axis=0) for p in range(n)}, index=out.index
    )
    out = pd.concat([out, probs], axis=1)
    return out.sort_values("exp_points", ascending=False)


def summarise(table: pd.DataFrame, top: int = 4, relegated: int = 3) -> pd.DataFrame:
    """Collapse the position distribution into title / top-N / relegation probabilities."""
    pos_cols = [c for c in table.columns if c.startswith("pos_")]
    return pd.DataFrame(
        {
            "played": table["played"],
            "points": table["points"],
            "exp_points": table["exp_points"].round(1),
            "p_title": table["pos_1"],
            f"p_top{top}": table[pos_cols[:top]].sum(axis=1),
            "p_relegation": table[pos_cols[-relegated:]].sum(axis=1),
        }
    )
