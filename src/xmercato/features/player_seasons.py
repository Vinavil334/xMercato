"""Player-season table from the Transfermarkt match data.

One row per player, season and club, for the first-tier domestic leagues of the dataset:
matchday squads (bench included, so that third goalkeepers are counted), matches, starts,
minutes, goals, assists, cards, the position he usually started in and his market value
at three dates (start of season, 1 January, end of season). The same numbers are kept for
the first half of the season alone, so that a January window can be studied with only
what was known on 1 January.

Seasons are named by their start year (2025 = 2025/26), as in the dataset. Leagues that
play within a calendar year follow the dataset's own labels.
"""

from __future__ import annotations

import pandas as pd

COLUMNS = [
    "player_id",
    "season",
    "club_id",
    "competition_id",
    "convocazioni",
    "partite",
    "titolare",
    "minuti",
    "gol",
    "assist",
    "gialli",
    "rossi",
    "partite_club",
    "convocazioni_h1",
    "partite_h1",
    "titolare_h1",
    "minuti_h1",
    "partite_club_h1",
    "posizione",
    "valore_inizio",
    "valore_gennaio",
    "valore_fine",
]


def league_games(games: pd.DataFrame, competitions: pd.DataFrame) -> pd.DataFrame:
    """Games of first-tier domestic leagues, with a flag for the first half of the season."""
    leagues = competitions.loc[competitions["type"] == "domestic_league", "competition_id"]
    out = games[games["competition_id"].isin(leagues)].copy()
    out["date"] = pd.to_datetime(out["date"])
    out["h1"] = out["date"] < pd.to_datetime(out["season"].astype(str) + "-12-31") + pd.Timedelta(
        days=1
    )
    return out[
        ["game_id", "competition_id", "season", "date", "home_club_id", "away_club_id", "h1"]
    ]


def club_games(league: pd.DataFrame) -> pd.DataFrame:
    """Number of league games of every club and season, in total and in the first half."""
    sides = pd.concat(
        [
            league.rename(columns={"home_club_id": "club_id"})[["club_id", "season", "h1"]],
            league.rename(columns={"away_club_id": "club_id"})[["club_id", "season", "h1"]],
        ]
    )
    return (
        sides.groupby(["club_id", "season"])
        .agg(partite_club=("h1", "size"), partite_club_h1=("h1", "sum"))
        .reset_index()
    )


def _value_at(valuations: pd.DataFrame, keys: pd.DataFrame, when: pd.Series) -> pd.Series:
    """Last market value of each player on or before ``when`` (NaN if none)."""
    left = keys.assign(_when=when.to_numpy().astype("datetime64[ns]"), _row=range(len(keys)))
    left = left.sort_values("_when")
    right = valuations.sort_values("date")
    merged = pd.merge_asof(
        left, right, left_on="_when", right_on="date", by="player_id", direction="backward"
    )
    return merged.set_index("_row")["market_value_in_eur"].sort_index().to_numpy()


def build(
    appearances: pd.DataFrame,
    lineups: pd.DataFrame,
    games: pd.DataFrame,
    competitions: pd.DataFrame,
    valuations: pd.DataFrame,
    first_season: int = 2018,
) -> pd.DataFrame:
    league = league_games(games, competitions)
    league = league[league["season"] >= first_season]
    info = league[["game_id", "competition_id", "season", "h1"]]

    apps = appearances.drop(columns=["competition_id"], errors="ignore").merge(info, on="game_id")
    apps = apps.rename(columns={"player_club_id": "club_id"}).assign(played=1)
    squads = lineups[["game_id", "player_id", "club_id", "type", "position"]].merge(
        info, on="game_id"
    )
    squads["start"] = (squads["type"] == "starting_lineup").astype(int)
    squads.loc[squads["start"] == 0, "position"] = None  # the usual position is where he starts
    # Everyone named in a matchday squad, plus anyone who played without a lineup record.
    apps = squads.drop(columns="type").merge(
        apps, on=["game_id", "player_id", "club_id", "competition_id", "season", "h1"], how="outer"
    )
    stats = ["played", "start", "minutes_played", "goals", "assists", "yellow_cards", "red_cards"]
    apps[stats] = apps[stats].fillna(0)

    keys = ["player_id", "season", "club_id", "competition_id"]
    first_half = apps[apps["h1"]]
    table = (
        apps.groupby(keys)
        .agg(
            convocazioni=("game_id", "size"),
            partite=("played", "sum"),
            titolare=("start", "sum"),
            minuti=("minutes_played", "sum"),
            gol=("goals", "sum"),
            assist=("assists", "sum"),
            gialli=("yellow_cards", "sum"),
            rossi=("red_cards", "sum"),
        )
        .join(
            first_half.groupby(keys).agg(
                convocazioni_h1=("game_id", "size"),
                partite_h1=("played", "sum"),
                titolare_h1=("start", "sum"),
                minuti_h1=("minutes_played", "sum"),
            )
        )
        .fillna({"convocazioni_h1": 0, "partite_h1": 0, "titolare_h1": 0, "minuti_h1": 0})
        .reset_index()
    )
    position = (
        apps.dropna(subset=["position"])
        .groupby(keys)["position"]
        .agg(lambda s: s.value_counts().index[0])
        .rename("posizione")
    )
    table = table.merge(position, on=keys, how="left")
    table = table.merge(club_games(league), on=["club_id", "season"], how="left")

    vals = valuations[["player_id", "date", "market_value_in_eur"]].copy()
    vals["date"] = pd.to_datetime(vals["date"]).astype("datetime64[ns]")
    season = table["season"].astype(str)
    for column, month_day, offset in [
        ("valore_inizio", "-08-01", 0),
        ("valore_gennaio", "-01-01", 1),
        ("valore_fine", "-07-01", 1),
    ]:
        year = (table["season"] + offset).astype(str) if offset else season
        table[column] = _value_at(vals, table[["player_id"]], pd.to_datetime(year + month_day))

    int_cols = [
        c for c in COLUMNS if c not in {"competition_id", "posizione"} and "valore" not in c
    ]
    table[int_cols] = table[int_cols].astype(int)
    return table[COLUMNS].sort_values(["season", "competition_id", "club_id", "player_id"])
