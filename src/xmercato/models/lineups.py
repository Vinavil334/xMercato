"""What absences cost a team in the league-table simulation.

A team's strength is fitted from results. An absence counts only once it shows in the
results; to count it in advance we need to know how much a player is worth to his team.
The measure used here is the market value of the likely starting eleven: a team whose
eleven is worth less than usual scores less and concedes more.

How much less comes from the bookmakers. Their closing odds already know the line-ups:
over 2,447 Serie A games (2019-2025), when a team's eleven was worth 10% less than its
usual one (log scale), the goals the bookmakers expected from it were about 1% lower and
those of its opponent 1.3% higher, once our results-only model had accounted for
everything else (:mod:`xmercato.evaluation.lineups_backtest`).

For the rest of the season, each team's eleven is rebuilt week by week with the players
who are out removed (hand-kept list, ``rose/indisponibili_*.csv``), and the average loss
of value turns into a factor on its goals scored and conceded.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from xmercato.recommend import availability


@dataclass(frozen=True)
class Effect:
    """Change in log expected goals per unit change in log value of the starting eleven."""

    own: float = 0.10  # on the team's own goals
    opponent: float = -0.13  # on the goals of its opponent, from the team's eleven


BOOKMAKERS = Effect()
UNKNOWN_RETURN_DAYS = 28  # an absence with no date is assumed to last four weeks


def eleven_value(squad: pd.DataFrame, usage: pd.DataFrame) -> pd.Series:
    """Value (millions) of each club's likely eleven: the most valuable players per slot.

    ``squad`` needs ``club``, ``slot`` and ``valore``; ``usage`` needs ``club``, ``slot``
    and ``titolari`` (starters per game).
    """
    starters = usage.set_index(["club", "slot"])["titolari"]
    total = {}
    for club, players in squad.groupby("club"):
        value = 0.0
        for slot, here in players.groupby("slot"):
            n = int(round(float(starters.get((club, slot), 0.0))))
            value += here["valore"].fillna(0).nlargest(n).sum()
        total[club] = value
    return pd.Series(total, name="valore_undici")


def season_end(season_start: int) -> pd.Timestamp:
    return pd.Timestamp(year=season_start + 1, month=5, day=31)


def absence_effect(
    squad: pd.DataFrame,
    usage: pd.DataFrame,
    absences: pd.DataFrame,
    start: pd.Timestamp,
    end: pd.Timestamp,
    effect: Effect = BOOKMAKERS,
) -> pd.DataFrame:
    """Per club: average loss of eleven value until ``end`` and the factors on its goals.

    The eleven is rebuilt every week between ``start`` and ``end``, without the players
    out that week. Returns ``club``, ``assenti`` (names), ``calo`` (average log change,
    negative), ``gol_fatti`` and ``gol_subiti`` (multipliers for the simulation).
    """
    squad = squad.dropna(subset=["slot"])
    index = availability.match(squad, absences)
    listed = absences.assign(row=index).dropna(subset=["row"])
    listed["fino"] = listed["rientro_stimato"].fillna(
        listed["aggiornato"] + pd.Timedelta(days=UNKNOWN_RETURN_DAYS)
    )
    listed = listed[listed["fino"] > start]
    full = eleven_value(squad, usage)
    weeks = pd.date_range(start, max(start, end), freq="7D")
    losses = []
    for day in weeks:
        out = listed[listed["fino"] > day]["row"].astype(int)
        value = eleven_value(squad.drop(index=out), usage).reindex(full.index).fillna(0)
        losses.append(np.log(value.clip(lower=0.5) / full.clip(lower=0.5)))
    loss = pd.concat(losses, axis=1).mean(axis=1) if losses else full * 0
    names = listed.assign(club=listed["club"]).groupby("club")["giocatore"].agg(", ".join)
    return pd.DataFrame(
        {
            "club": full.index,
            "assenti": full.index.map(names).fillna(""),
            "calo": loss.to_numpy(),
            "gol_fatti": np.exp(effect.own * loss.to_numpy()),
            "gol_subiti": np.exp(effect.opponent * loss.to_numpy()),
        }
    )
