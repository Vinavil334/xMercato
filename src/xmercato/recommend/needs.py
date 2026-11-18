"""Squad needs: which positions a club should strengthen, and why.

For every club and slot (see :mod:`xmercato.recommend.slots`) four signals are measured:

- **depth**: how many players the slot is missing, given how many starters the club
  fields there (from its lineups) and one backup per starter (three goalkeepers). Spare
  players in a neighbouring slot count half (a central midfielder can play behind the
  striker, a centre-back can play right-back in a back three);
- **quality**: how much less the slot's starters are worth than a typical starter of the
  same club (market value, log scale: +1 means half as much), compared with the same gap
  across the league, because goalkeepers and full-backs are always worth less than forwards;
- **age**: share of the slot's likely starters aged 31 or more;
- **expiring**: share of the slot's likely starters whose contract or loan ends by the
  next 30 June;
- **form** (optional): how the department and its attacking starters are doing this
  season against expectation (:mod:`xmercato.recommend.performance`).

The need score is a weighted sum; the weights depend on the window (in January depth and
quality matter, in summer age and contracts too) and are checked against the slots clubs
actually bought in past windows (:mod:`xmercato.evaluation.needs_backtest`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from xmercato.recommend.slots import SLOTS


@dataclass(frozen=True)
class NeedWeights:
    depth: float = 1.0
    quality: float = 0.5
    age: float = 0.0
    expiring: float = 0.0
    form: float = 0.0


# January weights checked on 2019-2022 and tested on 2023-2025 (docs/STUDIO.md): form is the
# only signal that clubs follow; the quality gap does not predict purchases and keeps a low
# weight as a reading of the squad. Summer weights are not checked yet.
WEIGHTS = {
    "gennaio": NeedWeights(depth=1.0, quality=0.25, age=0.0, expiring=0.1, form=1.2),
    "estate": NeedWeights(depth=1.0, quality=0.25, age=0.3, expiring=0.4, form=0.6),
}

OLD = 31  # age from which a starter counts as ageing
NEIGHBOURS = {
    "POR": (),
    "DC": ("TD", "TS"),
    "TD": ("DC", "TS"),
    "TS": ("DC", "TD"),
    "CC": ("TRQ",),
    "TRQ": ("CC", "ALI", "ATT"),
    "ALI": ("TRQ", "ATT"),
    "ATT": ("TRQ", "ALI"),
}
MISSING_VALUE_SHARE = 0.1  # a missing starter is worth this share of a typical starter


def usage(player_seasons: pd.DataFrame, club_of: Mapping[int, str], season: int) -> pd.DataFrame:
    """Starters per game in each slot, from the clubs' lineups in ``season``.

    ``player_seasons`` needs ``club_id``, ``season``, ``slot``, ``titolare`` and
    ``partite_club``; ``club_of`` maps Transfermarkt club ids to club names. Clubs without
    lineups that season (promoted from a league not covered) get the league average.
    """
    rows = player_seasons[
        (player_seasons["season"] == season) & player_seasons["club_id"].isin(club_of)
    ].dropna(subset=["slot"])
    per_club = (
        rows.groupby(["club_id", "slot"])["titolare"].sum()
        / rows.groupby("club_id")["partite_club"].max()
    ).unstack(fill_value=0.0)
    per_club = per_club.reindex(columns=list(SLOTS), fill_value=0.0)
    # Modal positions do not add up to exactly eleven: rescale.
    per_club = per_club.mul(11 / per_club.sum(axis=1), axis=0)
    average = per_club.mean() if len(per_club) else pd.Series(11 / len(SLOTS), index=SLOTS)
    clubs = sorted(set(club_of.values()))
    named = per_club.rename(index=dict(club_of))
    table = pd.DataFrame(
        [named.loc[c] if c in named.index else average for c in clubs], index=clubs
    )
    table.index.name = "club"
    return table.stack().rename("titolari").reset_index().rename(columns={"level_1": "slot"})


def required(starters: float, slot: str) -> int:
    """Players needed in a slot: three goalkeepers; elsewhere a backup for every starter."""
    if slot == "POR":
        return 3
    return 0 if starters < 0.25 else math.ceil(1.65 * starters - 1e-9)


def needs(
    squad: pd.DataFrame,
    usage_table: pd.DataFrame,
    window: str = "gennaio",
    weights: NeedWeights | None = None,
    form: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Need of every club in every slot, ranked within the club (1 = most urgent).

    ``squad`` needs ``club``, ``slot``, ``valore`` (millions), ``eta`` (years at the window)
    and ``in_scadenza`` (contract or loan ends by the next 30 June). ``form``, if given, has
    ``club``, ``slot``, ``forma`` (0-1) and ``nota_forma``.
    """
    weights = weights or WEIGHTS[window]
    squad = squad.dropna(subset=["slot"]).copy()
    squad["valore"] = squad["valore"].fillna(squad["valore"].min()).clip(lower=0.05)
    starters_used = usage_table.set_index(["club", "slot"])["titolari"]

    rows = []
    for club, players in squad.groupby("club"):
        # A typical starter: the eleven most valuable players of the squad.
        reference = float(np.exp(np.log(players["valore"].nlargest(11)).median()))
        used = {slot: float(starters_used.get((club, slot), 0.0)) for slot in SLOTS}
        count = players["slot"].value_counts().reindex(list(SLOTS), fill_value=0)
        need_n = {slot: required(used[slot], slot) for slot in SLOTS}
        spare = {slot: max(0, int(count[slot]) - need_n[slot]) for slot in SLOTS}
        for slot in SLOTS:
            here = players[players["slot"] == slot].sort_values("valore", ascending=False)
            n = max(1, round(used[slot])) if used[slot] >= 0.25 or slot == "POR" else 0
            cover = len(here) + 0.5 * sum(spare[other] for other in NEIGHBOURS[slot])
            missing = max(0.0, need_n[slot] - cover)
            top = here.head(n)
            values = list(top["valore"]) + [reference * MISSING_VALUE_SHARE] * (n - len(top))
            slot_value = float(np.exp(np.mean(np.log(values)))) if values else reference
            gap = math.log2(reference / slot_value) if n else 0.0
            old = float((top["eta"] >= OLD).mean()) if len(top) else 0.0
            ending = top["in_scadenza"].astype("boolean").fillna(False)
            expiring = float(ending.mean()) if len(top) else 0.0
            rows.append(
                {
                    "club": club,
                    "slot": slot,
                    "titolari": round(used[slot], 2),
                    "giocatori": len(here),
                    "servono": need_n[slot],
                    "mancano": math.ceil(missing),
                    "profondita": missing / need_n[slot] if need_n[slot] else 0.0,
                    "valore_titolari": round(slot_value, 2),
                    "valore_riferimento": round(reference, 2),
                    "divario_grezzo": gap,
                    "anziani": round(old, 2),
                    "in_scadenza": round(expiring, 2),
                    "titolari_nomi": ", ".join(top["giocatore"].astype(str))
                    if "giocatore" in top
                    else "",
                }
            )
    out = pd.DataFrame(rows)
    # Quality gap relative to the league: how much weaker than at the other clubs.
    typical = out[out["titolari"] >= 0.25].groupby("slot")["divario_grezzo"].median()
    out["divario"] = (out["divario_grezzo"] - out["slot"].map(typical).fillna(0)).round(2)
    if form is not None:
        out = out.merge(
            form[["club", "slot", "forma", "nota_forma"]], on=["club", "slot"], how="left"
        )
    else:
        out = out.assign(forma=0.0, nota_forma="")
    out["forma"] = out["forma"].fillna(0.0)
    out["nota_forma"] = out["nota_forma"].fillna("")
    out["punteggio"] = (
        weights.form * out["forma"]
        + weights.depth * out["profondita"]
        + weights.quality * out["divario"].clip(lower=0) * out["titolari"].clip(upper=1)
        + weights.age * out["anziani"]
        + weights.expiring * out["in_scadenza"]
    ).round(3)
    out["rango"] = (
        out.groupby("club")["punteggio"].rank(ascending=False, method="first").astype(int)
    )
    out["motivo"] = out.apply(explain, axis=1)
    return out.sort_values(["club", "rango"]).reset_index(drop=True)


def explain(row: pd.Series) -> str:
    """The reasons behind a need, in Italian, strongest first."""
    parts = []
    if row["mancano"]:
        players = "giocatore" if row["giocatori"] == 1 else "giocatori"
        parts.append(
            f"{row['giocatori']} {players} per {row['servono']} posti in rosa "
            f"(titolari per partita: {row['titolari']:.1f})"
        )
    if row["divario"] >= 0.5 and row["titolari"] >= 0.25:
        parts.append(
            f"i titolari valgono {row['valore_titolari']:.1f} mln contro i "
            f"{row['valore_riferimento']:.1f} di un titolare tipico della squadra, "
            "un distacco più ampio che nelle altre squadre"
        )
    if row["anziani"] > 0:
        parts.append("titolare con 31 anni o più")
    if row["in_scadenza"] > 0:
        parts.append("titolare in scadenza o in prestito fino a giugno")
    if row.get("forma", 0) > 0.05 and row.get("nota_forma"):
        parts.append("sotto le attese in questa stagione: " + row["nota_forma"])
    if not parts:
        return "reparto coperto"
    return "; ".join(parts)
