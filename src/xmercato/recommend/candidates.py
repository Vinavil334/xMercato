"""Candidates for a club: which players it could plausibly sign.

The pool is every player seen in a covered first-tier league the season before the window.
Each (club, player) pair gets a **plausibility** score from a logistic model trained on the
signings Serie A clubs actually made in past windows. What the model looks at:

- price: the player's market value against the value of a typical starter of the club;
- age, and how much he played last season;
- his league, Italian citizenship and whether he has already played in Serie A;
- how often his club and the buying club have done deals before.

Tried and left out because they did not improve the backtest: the strength of the player's
current club against the buying one, and the trend of his value during last season.

The model gives the chance that the club signs the player in the window: small numbers
(a club signs a handful of players out of thousands), useful to compare candidates. It
is not yet the probability of a *good* signing (that needs the
value and minutes projections of phases 2-4, see docs/ROADMAP.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize

LEAGUE_GROUPS = {
    "IT1": "Serie A",
    "GB1": "Premier League",
    "ES1": "Liga",
    "L1": "Bundesliga",
    "FR1": "Ligue 1",
    "PO1": "Portogallo",
    "NL1": "Olanda",
    "BE1": "Belgio",
    "TR1": "Turchia",
}
OTHER_LEAGUES = "altri campionati"

FEATURES = [
    "rel_valore",
    "rel_valore_2",
    "eta_c",
    "eta_c2",
    "minuti_quota",
    "minuti_quota_2",
    "italiano",
    "esperienza_a",
    "rapporti",
    *[f"camp_{g}" for g in [*LEAGUE_GROUPS.values(), OTHER_LEAGUES] if g != "Serie A"],
]


def pool(
    player_seasons: pd.DataFrame, players: pd.DataFrame, season: int, slot: pd.Series
) -> pd.DataFrame:
    """Players seen in ``season``: their main club, minutes share, value on 1 July after it.

    ``slot`` maps player ids to slots. Value: end of season, else 1 January, else start.
    """
    rows = player_seasons[player_seasons["season"] == season].sort_values("minuti")
    main = rows.groupby("player_id").tail(1).set_index("player_id")
    totals = rows.groupby("player_id")[["minuti", "partite_club"]].sum()
    value = main["valore_fine"].fillna(main["valore_gennaio"]).fillna(main["valore_inizio"])
    start_value = main["valore_inizio"].fillna(main["valore_gennaio"]).fillna(value)
    strength = club_strength(rows)
    italy_before = player_seasons[
        (player_seasons["competition_id"] == "IT1") & (player_seasons["season"] <= season)
    ]
    info = players.set_index("player_id")
    out = pd.DataFrame(
        {
            "player_id": main.index,
            "giocatore": main.index.map(info["name"]),
            "club_id": main["club_id"].to_numpy(),
            "competition_id": main["competition_id"].to_numpy(),
            "slot": main.index.map(slot),
            "valore": (value / 1e6).to_numpy(),
            "tendenza": np.log(value.clip(lower=1e4) / start_value.clip(lower=1e4)).to_numpy(),
            "forza_club": main["club_id"].map(strength).to_numpy(),
            "minuti": totals["minuti"].reindex(main.index).to_numpy(),
            "minuti_quota": (totals["minuti"] / (90 * totals["partite_club"]).clip(lower=1))
            .reindex(main.index)
            .clip(0, 1)
            .to_numpy(),
            "gol": main["gol"].to_numpy(),
            "assist": main["assist"].to_numpy(),
            "nascita": pd.to_datetime(main.index.map(info["date_of_birth"]), errors="coerce"),
            "cittadinanza": main.index.map(info["country_of_citizenship"]),
            "esperienza_a": main.index.isin(italy_before["player_id"]).astype(float),
        }
    )
    return out.dropna(subset=["valore", "slot"]).reset_index(drop=True)


def club_strength(rows: pd.DataFrame) -> pd.Series:
    """Value (millions) of a typical starter of every club: median of its eleven most valuable."""
    value = rows["valore_fine"].fillna(rows["valore_gennaio"]).fillna(rows["valore_inizio"])
    v = (value / 1e6).clip(lower=0.05).rename("v")
    top = rows.assign(v=v).dropna(subset=["v"]).groupby("club_id")["v"]
    return top.apply(lambda x: float(np.exp(np.log(x.nlargest(11)).median())))


def relations(transfers: pd.DataFrame, before: pd.Timestamp, years: int = 5) -> pd.Series:
    """Deals between each pair of clubs (either direction) in the ``years`` before a date."""
    date = pd.to_datetime(transfers["transfer_date"], errors="coerce")
    recent = transfers[(date < before) & (date >= before - pd.DateOffset(years=years))]
    a = recent[["from_club_id", "to_club_id"]].min(axis=1)
    b = recent[["from_club_id", "to_club_id"]].max(axis=1)
    return pd.Series(1, index=pd.MultiIndex.from_arrays([a, b])).groupby(level=[0, 1]).sum()


def features(
    candidates: pd.DataFrame,
    club_id: int,
    reference_value: float,
    deals: pd.Series,
    on: pd.Timestamp,
) -> pd.DataFrame:
    """Model inputs for every candidate of one club."""
    c = candidates
    rel = np.log(c["valore"].clip(lower=0.05) / max(reference_value, 0.05))
    eta = ((on - c["nascita"]).dt.days / 365.25).fillna(25.0)  # unknown birth date: neutral
    pair_a = np.minimum(c["club_id"], club_id)
    pair_b = np.maximum(c["club_id"], club_id)
    count = pd.Series(list(zip(pair_a, pair_b, strict=True))).map(deals).fillna(0).to_numpy()
    group = c["competition_id"].map(LEAGUE_GROUPS).fillna(OTHER_LEAGUES)
    out = pd.DataFrame(
        {
            "rel_valore": rel,
            "rel_valore_2": rel**2,
            "eta": eta,
            "eta_c": (eta - 25) / 4,
            "eta_c2": ((eta - 25) / 4) ** 2,
            "minuti_quota": c["minuti_quota"],
            "minuti_quota_2": c["minuti_quota"] ** 2,
            "italiano": (c["cittadinanza"] == "Italy").astype(float),
            "esperienza_a": c["esperienza_a"],
            "rapporti": np.log1p(count),
            "rel_club": np.log(
                c["forza_club"].fillna(reference_value) / max(reference_value, 0.05)
            ),
            "tendenza": c["tendenza"].fillna(0.0).clip(-2, 2),
        },
        index=c.index,
    )
    out["rel_club_2"] = out["rel_club"] ** 2
    for g in [*LEAGUE_GROUPS.values(), OTHER_LEAGUES]:
        if g != "Serie A":
            out[f"camp_{g}"] = (group == g).astype(float)
    return out


@dataclass
class PlausibilityModel:
    """Logistic regression with an L2 penalty, fitted on signings vs sampled non-signings."""

    l2: float = 1.0
    offset: float = 0.0  # log of the share of non-signings kept for training
    coef: np.ndarray = field(default_factory=lambda: np.zeros(0))
    intercept: float = 0.0
    mean: np.ndarray = field(default_factory=lambda: np.zeros(0))
    scale: np.ndarray = field(default_factory=lambda: np.ones(0))

    def fit(self, x: pd.DataFrame, y: np.ndarray, sampled_share: float = 1.0) -> PlausibilityModel:
        """``sampled_share``: share of the non-signings kept, to correct the intercept."""
        self.offset = float(np.log(sampled_share))
        raw = x[FEATURES].to_numpy(dtype=float)
        self.mean, self.scale = raw.mean(axis=0), raw.std(axis=0) + 1e-9
        z = (raw - self.mean) / self.scale
        design = np.column_stack([np.ones(len(z)), z])

        def loss(b: np.ndarray) -> tuple[float, np.ndarray]:
            eta = design @ b
            p = 1 / (1 + np.exp(-eta))
            nll = np.logaddexp(0, eta).sum() - y @ eta + 0.5 * self.l2 * (b[1:] ** 2).sum()
            grad = design.T @ (p - y)
            grad[1:] += self.l2 * b[1:]
            return nll, grad

        b = minimize(loss, np.zeros(design.shape[1]), jac=True, method="L-BFGS-B").x
        self.intercept, self.coef = float(b[0]), b[1:]
        return self

    def score(self, x: pd.DataFrame) -> np.ndarray:
        z = (x[FEATURES].to_numpy(dtype=float) - self.mean) / self.scale
        return z @ self.coef + self.intercept

    def probability(self, x: pd.DataFrame) -> np.ndarray:
        """Chance that the club signs the player in the window (intercept corrected)."""
        return 1 / (1 + np.exp(-(self.score(x) + self.offset)))

    def coefficients(self) -> pd.Series:
        """Effect of one standard deviation of each input on the log-odds."""
        return pd.Series(self.coef, index=FEATURES).round(3)
