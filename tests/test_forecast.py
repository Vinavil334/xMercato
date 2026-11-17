import numpy as np
import pandas as pd

from xmercato.models import forecast


def _season(teams, start, seed):
    rng = np.random.default_rng(seed)
    rows, day = [], pd.Timestamp(start)
    for h in teams:
        for a in teams:
            if h != a:
                rows.append((day, h, a, rng.poisson(1.5), rng.poisson(1.1)))
                day += pd.Timedelta(days=3)
    return pd.DataFrame(rows, columns=["date", "home", "away", "home_goals", "away_goals"])


def test_stack_and_start_of_season_fit():
    old = ["A", "B", "C", "D"]
    past = forecast.stack({2024: _season(old, "2024-08-20", 1), 2025: None})
    assert set(past["season"]) == {2024}
    # A new season with no matches yet: the fit still works from the past one,
    # the promoted team "E" starts from its prior and "D" (relegated) is left out.
    teams = ["A", "B", "C", "E"]
    config = forecast.GOALS.with_(history_seasons=1)
    fitted = forecast.fit_as_of(past, 2025, pd.Timestamp("2025-08-20"), config, teams)
    assert fitted.teams == tuple(teams)
    k = fitted.teams.index("E")
    assert fitted.attack[k] < fitted.attack.max()
    assert fitted.attack[k] < 0 and fitted.defence[k] < 0


def test_presets():
    assert forecast.CONFIGS["base"] == forecast.ModelConfig()
    assert forecast.CONFIGS["xg"].xg_share > 0 == forecast.CONFIGS["gol"].xg_share
