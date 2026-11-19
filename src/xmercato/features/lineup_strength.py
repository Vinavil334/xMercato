"""Market value of every starting eleven in Serie A, to measure what an absence costs.

For each league game and side: the market value (on the day of the game) of the eleven
starters, split into an attacking part (forwards, wingers, attacking midfielders and half
of the central midfielders) and a defensive part (goalkeeper, defenders and the other half
of the central midfielders). Comparing a team's eleven with its usual eleven tells how
weakened it was; :mod:`xmercato.models.lineups` turns that into goals.
"""

from __future__ import annotations

import pandas as pd

from xmercato.recommend.slots import slot_of

# Share of each slot's value that counts in attack (the rest counts in defence).
ATTACK_SHARE = {
    "POR": 0.0,
    "DC": 0.0,
    "TD": 0.0,
    "TS": 0.0,
    "CC": 0.5,
    "TRQ": 1.0,
    "ALI": 1.0,
    "ATT": 1.0,
}

COLUMNS = [
    "game_id", "date", "season", "club_id", "opponent_id", "home", "goals_for", "goals_against",
    "starters", "valued", "value_attack", "value_defence",
]  # fmt: skip


def build(
    games: pd.DataFrame,
    lineups: pd.DataFrame,
    valuations: pd.DataFrame,
    league: str = "IT1",
    first_season: int = 2018,
) -> pd.DataFrame:
    """One row per game and side, values in millions of euros.

    ``games`` needs the Transfermarkt columns ``game_id``, ``competition_id``, ``season``,
    ``date``, ``home_club_id``, ``away_club_id``, ``home_club_goals``, ``away_club_goals``.
    """
    g = games[(games["competition_id"] == league) & (games["season"] >= first_season)].copy()
    g["date"] = pd.to_datetime(g["date"])
    starters = lineups[
        (lineups["type"] == "starting_lineup") & lineups["game_id"].isin(g["game_id"])
    ][["game_id", "player_id", "club_id", "position"]]
    starters = starters.merge(g[["game_id", "date"]], on="game_id")

    vals = valuations[["player_id", "date", "market_value_in_eur"]].copy()
    vals["date"] = pd.to_datetime(vals["date"]).astype("datetime64[ns]")
    starters["date"] = starters["date"].astype("datetime64[ns]")
    starters = pd.merge_asof(
        starters.sort_values("date"),
        vals.sort_values("date"),
        on="date",
        by="player_id",
        direction="backward",
    )
    value = starters["market_value_in_eur"] / 1e6
    share = slot_of(starters["position"]).map(ATTACK_SHARE).fillna(0.5)
    starters = starters.assign(
        valued=value.notna().astype(int),
        value_attack=(value * share).fillna(0.0),
        value_defence=(value * (1 - share)).fillna(0.0),
    )
    sides = (
        starters.groupby(["game_id", "club_id"])
        .agg(
            starters=("player_id", "size"),
            valued=("valued", "sum"),
            value_attack=("value_attack", "sum"),
            value_defence=("value_defence", "sum"),
        )
        .reset_index()
    )
    home = g.rename(
        columns={"home_club_id": "club_id", "away_club_id": "opponent_id",
                 "home_club_goals": "goals_for", "away_club_goals": "goals_against"}
    ).assign(home=1)  # fmt: skip
    away = g.rename(
        columns={"away_club_id": "club_id", "home_club_id": "opponent_id",
                 "away_club_goals": "goals_for", "home_club_goals": "goals_against"}
    ).assign(home=0)  # fmt: skip
    both = pd.concat([home, away], ignore_index=True)
    out = both.merge(sides, on=["game_id", "club_id"], how="inner")
    out["date"] = out["date"].dt.date.astype(str)
    return out[COLUMNS].sort_values(["date", "game_id", "home"], ascending=[True, True, False])
