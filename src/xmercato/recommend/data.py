"""Tables used by the market pages: the hand-checked squads joined to the Transfermarkt data.

The Transfermarkt tables come from ``xmercato mercato dati`` (folder ``data/mercato``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from xmercato.recommend.slots import best_slot


@dataclass
class MarketData:
    player_seasons: pd.DataFrame
    players: pd.DataFrame
    transfers: pd.DataFrame
    clubs: pd.DataFrame


def load(folder: str | Path = "data/mercato") -> MarketData:
    folder = Path(folder)
    return MarketData(
        player_seasons=pd.read_csv(folder / "giocatori_stagioni.csv.gz"),
        players=pd.read_csv(folder / "giocatori.csv.gz", low_memory=False),
        transfers=pd.read_csv(folder / "trasferimenti_serie_a.csv.gz"),
        clubs=pd.read_csv(folder / "club.csv.gz"),
    )


def latest_position(player_seasons: pd.DataFrame, up_to_season: int) -> pd.Series:
    """Position each player usually started in, in his latest season up to ``up_to_season``."""
    rows = player_seasons[
        (player_seasons["season"] <= up_to_season) & player_seasons["posizione"].notna()
    ]
    rows = rows.sort_values(["season", "titolare"])
    return rows.groupby("player_id")["posizione"].last()


def age(birth: pd.Series, on: pd.Timestamp) -> pd.Series:
    return (on - pd.to_datetime(birth, errors="coerce")).dt.days / 365.25


def current_squad(
    squads: pd.DataFrame, data: MarketData, as_of: pd.Timestamp, last_season: int
) -> pd.DataFrame:
    """The squad file in the shape :func:`xmercato.recommend.needs.needs` wants.

    Slot: where the player started most in his latest covered season, else his
    Transfermarkt position, else the broad role of the squad file.
    """
    out = squads.copy().replace("", pd.NA)
    out["tm_id"] = pd.to_numeric(out["tm_id"], errors="coerce").astype("Int64")
    out["valore_mln"] = pd.to_numeric(out["valore_mln"], errors="coerce")
    ids = out["tm_id"]
    played = ids.map(latest_position(data.player_seasons, last_season))
    listed = ids.map(data.players.set_index("player_id")["sub_position"])
    out["slot"] = best_slot(played, listed, ruolo=out["ruolo"])
    out["valore"] = out["valore_mln"]
    out["eta"] = age(out["data_nascita"], as_of)
    season_end = pd.Timestamp(year=as_of.year + (as_of.month >= 7), month=6, day=30)
    contract_ends = pd.to_datetime(out["scadenza"], errors="coerce") <= season_end
    loan_ends = out["tipo"].isin(["prestito", "prestito_diritto"])
    out["in_scadenza"] = contract_ends | loan_ends
    return out
