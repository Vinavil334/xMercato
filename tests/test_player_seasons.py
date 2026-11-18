import pandas as pd
import pytest

from xmercato.features import player_seasons


@pytest.fixture
def tables():
    competitions = pd.DataFrame(
        {"competition_id": ["IT1", "CIT"], "type": ["domestic_league", "domestic_cup"],
         "country_name": ["Italy", "Italy"]}
    )  # fmt: skip
    games = pd.DataFrame(
        {
            "game_id": [1, 2, 3, 4],
            "competition_id": ["IT1", "IT1", "IT1", "CIT"],
            "season": [2025, 2025, 2025, 2025],
            "date": ["2025-09-01", "2025-12-20", "2026-02-01", "2025-11-01"],
            "home_club_id": [10, 20, 10, 10],
            "away_club_id": [20, 10, 20, 20],
        }
    )
    appearances = pd.DataFrame(
        {
            "game_id": [1, 2, 3, 4, 1],
            "player_id": [7, 7, 7, 7, 8],
            "player_club_id": [10, 10, 10, 10, 20],
            "minutes_played": [90, 30, 90, 90, 90],
            "goals": [1, 0, 2, 5, 0],
            "assists": [0, 1, 0, 0, 0],
            "yellow_cards": [0, 0, 1, 0, 0],
            "red_cards": [0, 0, 0, 0, 0],
        }
    )
    lineups = pd.DataFrame(
        {
            "game_id": [1, 2, 3, 1],
            "player_id": [7, 7, 7, 8],
            "club_id": [10, 10, 10, 20],
            "type": ["starting_lineup", "substitutes", "starting_lineup", "starting_lineup"],
            "position": ["Centre-Forward", "Left Winger", "Centre-Forward", "Goalkeeper"],
        }
    )
    valuations = pd.DataFrame(
        {
            "player_id": [7, 7, 7, 8],
            "date": ["2025-06-01", "2025-12-15", "2026-06-01", "2026-03-01"],
            "market_value_in_eur": [1e6, 2e6, 5e6, 3e5],
        }
    )
    return appearances, lineups, games, competitions, valuations


def test_build(tables):
    table = player_seasons.build(*tables, first_season=2025)
    row = table.set_index("player_id").loc[7]
    # Cup games are left out; the second half starts on 1 January.
    assert (row.partite, row.titolare, row.minuti, row.gol, row.assist) == (3, 2, 210, 3, 1)
    assert (row.partite_h1, row.titolare_h1, row.minuti_h1) == (2, 1, 120)
    assert (row.partite_club, row.partite_club_h1) == (3, 2)
    assert row.posizione == "Centre-Forward"
    assert (row.valore_inizio, row.valore_gennaio, row.valore_fine) == (1e6, 2e6, 5e6)
    keeper = table.set_index("player_id").loc[8]
    assert pd.isna(keeper.valore_inizio) and keeper.valore_fine == 3e5
    assert list(table.columns) == player_seasons.COLUMNS


def test_first_season_filter(tables):
    assert player_seasons.build(*tables, first_season=2026).empty
