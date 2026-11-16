"""Monte Carlo simulation of the rest of a double round-robin season.

Each fixture draws from its own random stream, identified by (seed, home, away). Two runs
with the same seed therefore give the *same* scoreline to every fixture whose expected
goals did not change, which is what makes "what if" comparisons clean: tweak one team and
only the matches involving that team move.

Known simplification: ties in the table are broken by goal difference, then goals
scored, then at random. Serie A actually uses head-to-head records, and a play-off
when the title or the last relegation place is tied on points.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import poisson as poisson_dist

from xmercato.models.poisson import TeamStrengths

_MAX_GOALS = 25  # scorelines above this are cut off; irrelevant at football scoring rates


def remaining_fixtures(results: pd.DataFrame, teams: list[str] | tuple[str, ...]) -> pd.DataFrame:
    """Fixtures still to play: every ordered (home, away) pair not found in ``results``."""
    played = set(zip(results["home"], results["away"], strict=True))
    todo = [(h, a) for h in teams for a in teams if h != a and (h, a) not in played]
    return pd.DataFrame(todo, columns=["home", "away"])


def _check_fixed(fixed: pd.DataFrame, todo: pd.DataFrame) -> None:
    pairs = list(zip(fixed["home"], fixed["away"], strict=True))
    if len(set(pairs)) != len(pairs):
        raise ValueError("The same fixture is fixed more than once")
    unknown = set(pairs) - set(zip(todo["home"], todo["away"], strict=True))
    if unknown:
        raise ValueError(f"Fixed results for fixtures that are not left to play: {sorted(unknown)}")


def _draw_goals(lam: np.ndarray, streams: list[np.random.Generator], n_sims: int) -> np.ndarray:
    """Poisson goals by inverse CDF, one column per fixture, one random stream per fixture.

    Inverse-CDF sampling makes goals monotone in ``lam`` for a given stream: raising a
    team's expected goals can only raise its simulated goals, never reshuffle them.
    """
    cdf = poisson_dist.cdf(np.arange(_MAX_GOALS)[None, :], lam[:, None])
    goals = np.empty((n_sims, len(lam)), dtype=np.int64)
    for j, stream in enumerate(streams):
        goals[:, j] = np.searchsorted(cdf[j], stream.random(n_sims), side="right")
    return goals


def simulate(
    strengths: TeamStrengths,
    results: pd.DataFrame,
    n_sims: int = 10_000,
    seed: int | None = None,
    fixed: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Simulate the remaining fixtures ``n_sims`` times.

    ``fixed`` optionally pins the score of fixtures still to play (same columns as
    ``results``): they count towards the final table but not towards ``played``/``points``.

    Returns one row per team, sorted by expected points, with current points, expected
    final points and the probability of each final position (columns ``pos_1`` ... ``pos_N``).
    """
    teams = strengths.teams
    n = len(teams)
    index = {team: k for k, team in enumerate(teams)}
    if seed is None:
        seed = int(np.random.SeedSequence().generate_state(1)[0])

    def tally(matches: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        pts, gf, ga = np.zeros(n), np.zeros(n), np.zeros(n)
        h = matches["home"].map(index).to_numpy(dtype=int)
        a = matches["away"].map(index).to_numpy(dtype=int)
        gh = matches["home_goals"].to_numpy()
        gaw = matches["away_goals"].to_numpy()
        np.add.at(pts, h, 3 * (gh > gaw) + (gh == gaw))
        np.add.at(pts, a, 3 * (gaw > gh) + (gh == gaw))
        np.add.at(gf, h, gh)
        np.add.at(gf, a, gaw)
        np.add.at(ga, h, gaw)
        np.add.at(ga, a, gh)
        return pts, gf, ga

    points, goals_for, goals_against = tally(results)
    played = np.bincount(results["home"].map(index), minlength=n) + np.bincount(
        results["away"].map(index), minlength=n
    )

    todo = remaining_fixtures(results, teams)
    base_points, base_gf, base_ga = points.copy(), goals_for.copy(), goals_against.copy()
    if fixed is not None and len(fixed):
        _check_fixed(fixed, todo)
        fixed_points, fixed_gf, fixed_ga = tally(fixed)
        base_points += fixed_points
        base_gf += fixed_gf
        base_ga += fixed_ga
        pinned = set(zip(fixed["home"], fixed["away"], strict=True))
        keep = [pair not in pinned for pair in zip(todo["home"], todo["away"], strict=True)]
        todo = todo[keep].reset_index(drop=True)

    # Remaining fixtures, simulated all at once: arrays are (n_sims, n_fixtures).
    fh = todo["home"].map(index).to_numpy(dtype=int)
    fa = todo["away"].map(index).to_numpy(dtype=int)
    lam_h = np.exp(strengths.mu + strengths.home_adv + strengths.attack[fh] - strengths.defence[fa])
    lam_a = np.exp(strengths.mu + strengths.attack[fa] - strengths.defence[fh])
    fixture_id = fh * n + fa
    sim_h = _draw_goals(lam_h, [np.random.default_rng([seed, 0, f]) for f in fixture_id], n_sims)
    sim_a = _draw_goals(lam_a, [np.random.default_rng([seed, 1, f]) for f in fixture_id], n_sims)

    # Fixture-to-team incidence matrices turn per-fixture outcomes into per-team totals.
    home_of = np.zeros((len(todo), n))
    away_of = np.zeros((len(todo), n))
    home_of[np.arange(len(todo)), fh] = 1
    away_of[np.arange(len(todo)), fa] = 1

    draw = sim_h == sim_a
    final_points = (
        base_points
        + (3 * (sim_h > sim_a) + draw) @ home_of
        + (3 * (sim_a > sim_h) + draw) @ away_of
    )
    final_gf = base_gf + sim_h @ home_of + sim_a @ away_of
    final_ga = base_ga + sim_a @ home_of + sim_h @ away_of

    # Rank: points, then goal difference, then goals scored, then a random draw.
    tie_break = np.random.default_rng([seed, 2]).random((n_sims, n))
    key = final_points * 1e7 + (final_gf - final_ga + 500) * 1e4 + final_gf * 10 + tie_break
    order = np.argsort(-key, axis=1)
    position = np.empty_like(order)
    position[np.arange(n_sims)[:, None], order] = np.arange(n)

    out = pd.DataFrame(
        {
            "played": played,
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
