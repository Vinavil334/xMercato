import pandas as pd
import pytest

from xmercato.features import lineup_strength


def test_build():
    games = pd.DataFrame(
        {"game_id": [1, 2], "competition_id": ["IT1", "CIT"], "season": [2025, 2025],
         "date": ["2025-09-01", "2025-09-05"], "home_club_id": [10, 10], "away_club_id": [20, 20],
         "home_club_goals": [2, 0], "away_club_goals": [1, 0]}
    )  # fmt: skip
    lineups = pd.DataFrame(
        {"game_id": [1, 1, 1, 1], "player_id": [7, 8, 9, 5], "club_id": [10, 10, 20, 10],
         "type": ["starting_lineup", "starting_lineup", "starting_lineup", "substitutes"],
         "position": ["Centre-Forward", "Central Midfield", "Goalkeeper", "Centre-Back"]}
    )  # fmt: skip
    valuations = pd.DataFrame(
        {"player_id": [7, 8, 9, 7],
         "date": ["2025-06-01", "2025-06-01", "2025-06-01", "2025-10-01"],
         "market_value_in_eur": [20e6, 10e6, 4e6, 99e6]}
    )  # fmt: skip
    out = lineup_strength.build(games, lineups, valuations).set_index("club_id")
    assert list(out.columns) == [c for c in lineup_strength.COLUMNS if c != "club_id"]
    home = out.loc[10]
    # Forward fully in attack, central midfielder half and half; the later value is not used.
    assert home["value_attack"] == pytest.approx(25.0)
    assert home["value_defence"] == pytest.approx(5.0)
    assert (home["starters"], home["home"], home["goals_for"], home["goals_against"]) == (
        2,
        1,
        2,
        1,
    )
    away = out.loc[20]
    assert away["value_defence"] == pytest.approx(4.0) and away["home"] == 0
    assert len(out) == 2  # the cup game is left out
