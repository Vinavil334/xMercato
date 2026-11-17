"""Independent-Poisson team strength model (Maher, 1982).

Goals are modelled as

    home goals ~ Poisson(exp(mu + home_adv + attack[home] - defence[away]))
    away goals ~ Poisson(exp(mu           + attack[away] - defence[home]))

Attack and defence parameters are shrunk towards zero (the league average) with an
L2 penalty. With few matches per team, typical early in a season and for promoted
sides, the unpenalised fit is unstable; the penalty plays the role of a prior.

This is the baseline. Planned upgrades are in docs/ROADMAP.md: xG instead of goals,
time decay, Dixon-Coles low-score correction, and priors built from squad strength.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd
from scipy.optimize import minimize


@dataclass(frozen=True)
class TeamStrengths:
    """Fitted parameters. ``attack`` and ``defence`` are indexed by team name."""

    teams: tuple[str, ...]
    attack: np.ndarray
    defence: np.ndarray
    mu: float
    home_adv: float

    def expected_goals(self, home: str, away: str) -> tuple[float, float]:
        """Expected goals (home, away) for a single fixture."""
        i, j = self.teams.index(home), self.teams.index(away)
        lam_home = np.exp(self.mu + self.home_adv + self.attack[i] - self.defence[j])
        lam_away = np.exp(self.mu + self.attack[j] - self.defence[i])
        return float(lam_home), float(lam_away)

    def scaled(
        self,
        goals_for: dict[str, float] | None = None,
        goals_against: dict[str, float] | None = None,
    ) -> TeamStrengths:
        """Copy with some teams made stronger or weaker, for "what if" scenarios.

        ``goals_for={"Inter": 1.10}`` makes Inter score 10% more against everyone;
        ``goals_against={"Inter": 0.90}`` makes Inter concede 10% fewer.
        """
        attack, defence = self.attack.copy(), self.defence.copy()
        for team, factor in (goals_for or {}).items():
            if factor <= 0:
                raise ValueError(f"Scaling factor must be positive, got {factor} for {team}")
            attack[self.teams.index(team)] += np.log(factor)
        for team, factor in (goals_against or {}).items():
            if factor <= 0:
                raise ValueError(f"Scaling factor must be positive, got {factor} for {team}")
            defence[self.teams.index(team)] -= np.log(factor)
        return replace(self, attack=attack, defence=defence)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {"attack": self.attack, "defence": self.defence},
            index=pd.Index(self.teams, name="team"),
        )


def fit(
    results: pd.DataFrame,
    teams: list[str] | None = None,
    shrinkage: float = 2.0,
) -> TeamStrengths:
    """Fit team strengths by penalised maximum likelihood.

    ``results`` needs columns ``home, away, home_goals, away_goals``.
    ``teams`` lets the caller include sides with no matches yet: they get league-average
    strength. ``shrinkage`` is the L2 penalty weight; 0 gives the plain Maher model.
    """
    if teams is None:
        teams = sorted(set(results["home"]) | set(results["away"]))
    unknown = (set(results["home"]) | set(results["away"])) - set(teams)
    if unknown:
        raise ValueError(f"Results contain teams not in `teams`: {sorted(unknown)}")

    index = {team: k for k, team in enumerate(teams)}
    n = len(teams)
    h = results["home"].map(index).to_numpy()
    a = results["away"].map(index).to_numpy()
    gh = results["home_goals"].to_numpy(dtype=float)
    ga = results["away_goals"].to_numpy(dtype=float)

    def unpack(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
        return x[:n], x[n : 2 * n], x[2 * n], x[2 * n + 1]

    def objective(x: np.ndarray) -> tuple[float, np.ndarray]:
        att, dfn, mu, home = unpack(x)
        log_h = mu + home + att[h] - dfn[a]
        log_a = mu + att[a] - dfn[h]
        lam_h, lam_a = np.exp(log_h), np.exp(log_a)
        nll = np.sum(lam_h - gh * log_h) + np.sum(lam_a - ga * log_a)
        nll += 0.5 * shrinkage * (att @ att + dfn @ dfn)

        res_h, res_a = lam_h - gh, lam_a - ga
        g_att = np.bincount(h, res_h, n) + np.bincount(a, res_a, n) + shrinkage * att
        g_dfn = -np.bincount(a, res_h, n) - np.bincount(h, res_a, n) + shrinkage * dfn
        grad = np.concatenate([g_att, g_dfn, [res_h.sum() + res_a.sum(), res_h.sum()]])
        return float(nll), grad

    x0 = np.zeros(2 * n + 2)
    if len(results):
        x0[2 * n] = np.log(max((gh.sum() + ga.sum()) / (2 * len(results)), 0.1))
    opt = minimize(objective, x0, jac=True, method="L-BFGS-B")
    if not opt.success:
        raise RuntimeError(f"Poisson fit did not converge: {opt.message}")

    att, dfn, mu, home = unpack(opt.x)
    # Attack and defence are identified only up to a constant: centre them.
    shift_att, shift_dfn = att.mean(), dfn.mean()
    return TeamStrengths(
        teams=tuple(teams),
        attack=att - shift_att,
        defence=dfn - shift_dfn,
        mu=float(mu + shift_att - shift_dfn),
        home_adv=float(home),
    )
