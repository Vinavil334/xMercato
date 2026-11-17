import numpy as np
import pandas as pd
import pytest

from xmercato.evaluation import backtest
from xmercato.models import forecast


def _league(seasons=(2020, 2021), seed=0):
    """Two double round-robins per season from known strengths; one team is replaced."""
    rng = np.random.default_rng(seed)
    rows = []
    for k, season in enumerate(seasons):
        teams = [f"T{i}" for i in range(6)] if k == 0 else [*[f"T{i}" for i in range(5)], "New"]
        strength = {t: 0.3 * (3 - i) for i, t in enumerate(teams)}
        strength["New"] = -0.6
        day = pd.Timestamp(f"{season}-08-20")
        for _rep in range(2):
            for h in teams:
                for a in teams:
                    if h == a:
                        continue
                    lh = np.exp(0.2 + 0.25 + strength[h] - (-strength[a]) * 0.5)
                    la = np.exp(0.2 + strength[a] - (-strength[h]) * 0.5)
                    rows.append((season, day, h, a, rng.poisson(lh), rng.poisson(la)))
                    day += pd.Timedelta(days=2)
    df = pd.DataFrame(rows, columns=["season", "date", "home", "away", "home_goals", "away_goals"])
    df["home_xg"] = df["home_goals"] * 0.8 + 0.3
    df["away_xg"] = df["away_goals"] * 0.8 + 0.3
    df["odds_home"], df["odds_draw"], df["odds_away"] = 2.0, 3.4, 3.8
    return df


def test_predictions_use_only_the_past():
    df = _league()
    preds = backtest.predict_season(df, 2021, forecast.ModelConfig(history_seasons=1))
    assert len(preds) == (df["season"] == 2021).sum()
    assert np.allclose(preds[["p_home", "p_draw", "p_away"]].sum(axis=1), 1)
    # Changing a *later* result must not change an earlier prediction.
    later = df.copy()
    last = later.index[later["season"] == 2021][-1]
    later.loc[last, "home_goals"] = 9
    again = backtest.predict_season(later, 2021, forecast.ModelConfig(history_seasons=1))
    pd.testing.assert_frame_equal(preds.iloc[:-1], again.iloc[:-1])


def test_promoted_teams_and_their_prior():
    df = _league()
    assert forecast.promoted_teams(df, 2021) == {"New"}
    assert forecast.promoted_teams(df, 2020) == set()
    first_day = df.loc[df["season"] == 2021, "date"].min()
    teams = set(df.loc[df["season"] == 2021, "home"])
    plain = forecast.fit_as_of(df, 2021, first_day, forecast.ModelConfig(history_seasons=1), teams)
    with_prior = forecast.fit_as_of(
        df, 2021, first_day,
        forecast.ModelConfig(history_seasons=1, promoted_prior=(-0.4, -0.3)), teams,
    )  # fmt: skip
    k = plain.teams.index("New")
    assert with_prior.attack[k] < plain.attack[k]


def test_xg_targets_fall_back_to_goals():
    df = _league().assign(home_xg=np.nan, away_xg=np.nan)
    t = forecast.targets(df, 0.5)
    assert (t["t_home"] == df["home_goals"]).all()


def test_scores_and_bookmaker():
    df = _league().head(3).assign(home_goals=[2, 1, 0], away_goals=[0, 1, 3])
    scored = backtest.score(backtest.bookmaker_probabilities(df))
    p = 1 / np.array([2.0, 3.4, 3.8])
    p /= p.sum()
    assert scored["log_loss"].iloc[0] == pytest.approx(-np.log(p[0]))
    assert scored["log_loss"].iloc[1] == pytest.approx(-np.log(p[1]))
    # RPS of a certain, correct forecast is 0; of a certain, wrong one is at most 1.
    perfect = df.assign(p_home=[1.0, 0, 0], p_draw=[0, 1.0, 0], p_away=[0, 0, 1.0])
    assert backtest.score(perfect)["rps"].max() == 0
    summary = backtest.summary(scored)
    assert summary.loc["bookmaker", "partite"] == 3


def test_table_errors():
    df = _league()
    errors = backtest.table_errors(
        df, 2021, forecast.ModelConfig(history_seasons=1), rounds=(0, 5), n_sims=200
    )
    assert list(errors["round"]) == [0, 5]
    assert (errors["mae"] >= 0).all()
    # The current-season-only model has nothing to fit on before round 1.
    only = backtest.table_errors(df, 2021, forecast.ModelConfig(), rounds=(0, 5), n_sims=200)
    assert list(only["round"]) == [5]


def test_final_points():
    df = pd.DataFrame(
        {"home": ["A", "B"], "away": ["B", "A"], "home_goals": [1, 0], "away_goals": [0, 0]}
    )
    assert backtest.final_points(df).to_dict() == {"A": 4, "B": 1}
