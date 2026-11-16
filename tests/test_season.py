from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from xmercato.ingest import football_data
from xmercato.models import poisson
from xmercato.sim import season

FIXTURE = Path(__file__).parent / "data" / "serie_a_2025_26.csv"


@pytest.fixture(scope="module")
def results():
    return football_data.load_results(FIXTURE)


def test_remaining_fixtures_complete_the_round_robin(results):
    teams = sorted(set(results["home"]))
    half = results.iloc[:190]
    todo = season.remaining_fixtures(half, teams)
    assert len(todo) == 380 - 190
    assert len(season.remaining_fixtures(results, teams)) == 0


def test_finished_season_reproduces_the_points(results):
    teams = sorted(set(results["home"]))
    strengths = poisson.fit(results, teams=teams)
    table = season.simulate(strengths, results, n_sims=50, seed=1)

    expected = pd.Series(0, index=teams)
    for row in results.itertuples():
        if row.home_goals > row.away_goals:
            expected[row.home] += 3
        elif row.home_goals < row.away_goals:
            expected[row.away] += 3
        else:
            expected[row.home] += 1
            expected[row.away] += 1
    assert (table["points"] == expected[table.index]).all()
    assert np.allclose(table["exp_points"], table["points"])
    assert (table["played"] == 38).all()


def test_position_probabilities_are_a_distribution(results):
    teams = sorted(set(results["home"]))
    half = results.iloc[:190]
    strengths = poisson.fit(half, teams=teams)
    table = season.simulate(strengths, half, n_sims=2000, seed=7)
    pos = table.filter(like="pos_")
    assert pos.shape == (20, 20)
    assert np.allclose(pos.sum(axis=1), 1.0)  # each team ends somewhere
    assert np.allclose(pos.sum(axis=0), 1.0)  # each place is taken by one team

    summary = season.summarise(table)
    assert summary["p_title"].sum() == pytest.approx(1.0)
    assert summary["p_top4"].sum() == pytest.approx(4.0)
    assert summary["p_relegation"].sum() == pytest.approx(3.0)


def test_same_seed_same_result(results):
    teams = sorted(set(results["home"]))
    half = results.iloc[:190]
    strengths = poisson.fit(half, teams=teams)
    a = season.simulate(strengths, half, n_sims=500, seed=3)
    b = season.simulate(strengths, half, n_sims=500, seed=3)
    pd.testing.assert_frame_equal(a, b)
