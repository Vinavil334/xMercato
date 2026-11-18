"""Backtest of squad needs: did clubs buy in the slots ranked as their biggest needs?

For each past window the squad is rebuilt from the Transfermarkt data as it was before the
window opened:

- **January of season S**: everyone in a Serie A matchday squad of the club between August
  and December; values on 1 January; usage of the slots from the club's lineups in S-1.
- **Summer before season S**: everyone in a matchday squad of the club in S-1; values on
  1 July. Departures of that summer are not known in advance, as in real life.

Contracts are not in the historical data, so the "expiring" signal is left out here.
The arrivals of the window (loan returns and youth promotions excluded) are then compared
with the club's need ranking.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
import pandas as pd

from xmercato.recommend import needs as nd
from xmercato.recommend.data import age, latest_position
from xmercato.recommend.slots import SLOTS, best_slot

YOUTH = r"(?i)\bU-?1\d\b|\bU-?2[0-3]\b|primavera|youth|juniores|next gen|under ?2\d|\bB\b$"


def window_dates(season: int, window: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    if window == "gennaio":
        return pd.Timestamp(f"{season + 1}-01-01"), pd.Timestamp(f"{season + 1}-02-10")
    return pd.Timestamp(f"{season}-06-01"), pd.Timestamp(f"{season}-09-05")


def with_slots(player_seasons: pd.DataFrame, players: pd.DataFrame, up_to: int) -> pd.Series:
    """Slot of every player as known at the end of season ``up_to``."""
    ids = pd.Series(players["player_id"].to_numpy(), index=players["player_id"].to_numpy())
    return best_slot(
        ids.map(latest_position(player_seasons, up_to)),
        ids.map(players.set_index("player_id")["sub_position"]),
    )


def squad_before(
    player_seasons: pd.DataFrame,
    players: pd.DataFrame,
    season: int,
    window: str,
    league: str = "IT1",
) -> pd.DataFrame:
    """Squads of every club of ``league`` just before the window, in the shape needs() wants."""
    if window == "gennaio":
        rows = player_seasons[
            (player_seasons["season"] == season)
            & (player_seasons["competition_id"] == league)
            & (player_seasons["convocazioni_h1"] > 0)
        ]
        value, slot_season = rows["valore_gennaio"], season - 1
    else:
        rows = player_seasons[
            (player_seasons["season"] == season - 1) & (player_seasons["competition_id"] == league)
        ]
        value, slot_season = rows["valore_fine"], season - 1
    start, _ = window_dates(season, window)
    slot = with_slots(player_seasons, players, slot_season)
    birth = players.set_index("player_id")["date_of_birth"]
    return pd.DataFrame(
        {
            "club": rows["club_id"].to_numpy(),
            "player_id": rows["player_id"].to_numpy(),
            "slot": rows["player_id"].map(slot).to_numpy(),
            "valore": (value / 1e6).to_numpy(),
            "eta": age(rows["player_id"].map(birth), start).to_numpy(),
            "in_scadenza": False,
        }
    )


def clubs_of_season(player_seasons: pd.DataFrame, season: int, league: str = "IT1") -> set[int]:
    rows = player_seasons[
        (player_seasons["season"] == season) & (player_seasons["competition_id"] == league)
    ]
    return set(rows["club_id"])


def arrivals(
    transfers: pd.DataFrame,
    clubs: Iterable[int],
    season: int,
    window: str,
) -> pd.DataFrame:
    """Players who joined ``clubs`` in the window: no loan returns, no youth promotions."""
    start, end = window_dates(season, window)
    t = transfers.assign(date=pd.to_datetime(transfers["transfer_date"], errors="coerce"))
    moves = t[t["to_club_id"].isin(set(clubs)) & t["date"].between(start, end)]
    # A loan return: the player had earlier moved from the club he now "joins".
    earlier = t[["player_id", "from_club_id", "to_club_id", "date"]].rename(
        columns={"from_club_id": "e_from", "to_club_id": "e_to", "date": "e_date"}
    )
    back = moves.merge(earlier, on="player_id")
    back = back[
        (back["e_from"] == back["to_club_id"])
        & (back["e_to"] == back["from_club_id"])
        & (back["e_date"] < back["date"])
    ]
    moves = moves[~moves.set_index(["player_id", "date"]).index.isin(
        back.set_index(["player_id", "date"]).index
    )]  # fmt: skip
    moves = moves[~moves["from_club_name"].astype(str).str.contains(YOUTH, regex=True)]
    return moves


def evaluate(
    player_seasons: pd.DataFrame,
    players: pd.DataFrame,
    transfers: pd.DataFrame,
    seasons: Iterable[int],
    window: str,
    weights: nd.NeedWeights | None = None,
) -> pd.DataFrame:
    """One row per arrival: its slot and the rank of that slot among the club's needs."""
    ps = player_seasons.assign(
        slot=best_slot(
            player_seasons["posizione"],
            player_seasons["player_id"].map(players.set_index("player_id")["sub_position"]),
        )
    )
    rows = []
    for season in seasons:
        clubs = clubs_of_season(ps, season)
        if window == "estate":
            clubs &= clubs_of_season(ps, season - 1)  # promoted clubs: no squad to start from
        squad = squad_before(ps, players, season, window)
        squad = squad[squad["club"].isin(clubs)]
        club_of: Mapping[int, int] = {c: c for c in clubs}
        usage = nd.usage(ps, club_of, season - 1)
        ranking = nd.needs(squad, usage, window, weights)
        rank = ranking.set_index(["club", "slot"])["rango"]
        came = arrivals(transfers, clubs, season, window)
        came = came.assign(
            slot=came["player_id"].map(with_slots(ps, players, season - (window == "estate")))
        ).dropna(subset=["slot"])
        for _, move in came.iterrows():
            rows.append(
                {
                    "season": season,
                    "window": window,
                    "club_id": move["to_club_id"],
                    "player_id": move["player_id"],
                    "giocatore": move["player_name"],
                    "slot": move["slot"],
                    "rango": int(rank.get((move["to_club_id"], move["slot"]), len(SLOTS))),
                }
            )
    return pd.DataFrame(rows)


def baseline_ranks(results: pd.DataFrame, train: pd.DataFrame) -> pd.Series:
    """Rank of each arrival's slot if every club simply bought the most bought slots."""
    order = train["slot"].value_counts().reindex(list(SLOTS), fill_value=0)
    rank = order.rank(ascending=False, method="first").astype(int)
    return results["slot"].map(rank)


def summary(ranks: pd.Series) -> dict[str, float]:
    """Share of arrivals in the top 1, 2 and 3 needs, and mean reciprocal rank."""
    r = ranks.to_numpy()
    return {
        "acquisti": len(r),
        "primo": float(np.mean(r <= 1)),
        "primi_2": float(np.mean(r <= 2)),
        "primi_3": float(np.mean(r <= 3)),
        "mrr": float(np.mean(1 / r)),
    }
