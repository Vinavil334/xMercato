import numpy as np
import pandas as pd
import pytest

from xmercato.ingest import football_data
from xmercato.models import poisson
from xmercato.sim import season

FIXTURE = football_data.SAMPLE_SEASON


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


@pytest.fixture(scope="module")
def half(results):
    return results.iloc[:190]


@pytest.fixture(scope="module")
def strengths(results, half):
    return poisson.fit(half, teams=sorted(set(results["home"])))


def test_unchanged_teams_keep_their_simulated_matches(strengths, half):
    """Boosting one team must not reshuffle matches that team does not play in."""
    base = season.simulate(strengths, half, n_sims=3000, seed=11)
    boosted = season.simulate(
        strengths.scaled(goals_for={"Inter": 1.3}), half, n_sims=3000, seed=11
    )
    assert boosted.loc["Inter", "exp_points"] > base.loc["Inter", "exp_points"]
    # Everyone else can only lose points, and only in their matches against Inter (at most 2 left).
    others = base.index.drop("Inter")
    diff = boosted.loc[others, "exp_points"] - base.loc[others, "exp_points"]
    assert (diff <= 1e-9).all()
    assert (diff > -1.0).all()


def test_neutral_scaling_changes_nothing(strengths, half):
    base = season.simulate(strengths, half, n_sims=500, seed=5)
    same = season.simulate(
        strengths.scaled(goals_for={"Roma": 1.0}, goals_against={"Roma": 1.0}),
        half,
        n_sims=500,
        seed=5,
    )
    pd.testing.assert_frame_equal(base, same)


def test_fixed_results_are_counted(strengths, half):
    teams = strengths.teams
    todo = season.remaining_fixtures(half, teams)
    # Pin every remaining fixture to 1-0: the final table is then fully determined.
    fixed = todo.assign(home_goals=1, away_goals=0)
    table = season.simulate(strengths, half, n_sims=20, seed=0, fixed=fixed)
    current = table["points"]
    home_wins_left = fixed.groupby("home").size().reindex(table.index, fill_value=0)
    assert np.allclose(table["exp_points"], current + 3 * home_wins_left)
    # Current standings still describe real matches only.
    assert table["played"].sum() == 2 * len(half)


def test_fixing_one_result_moves_only_that_match(strengths, half):
    todo = season.remaining_fixtures(half, strengths.teams)
    home, away = todo.iloc[0]
    fixed = pd.DataFrame([{"home": home, "away": away, "home_goals": 0, "away_goals": 3}])
    base = season.simulate(strengths, half, n_sims=2000, seed=9)
    scenario = season.simulate(strengths, half, n_sims=2000, seed=9, fixed=fixed)
    diff = (scenario["exp_points"] - base["exp_points"]).round(9)
    assert set(diff[diff != 0].index) == {home, away}
    assert diff[away] > 0 > diff[home]


def test_fixed_results_must_be_left_to_play(strengths, half):
    played = half.iloc[[0]][["home", "away", "home_goals", "away_goals"]]
    with pytest.raises(ValueError, match="not left to play"):
        season.simulate(strengths, half, n_sims=10, seed=0, fixed=played)
    todo = season.remaining_fixtures(half, strengths.teams).iloc[[0, 0]]
    with pytest.raises(ValueError, match="more than once"):
        season.simulate(
            strengths, half, n_sims=10, seed=0, fixed=todo.assign(home_goals=1, away_goals=1)
        )
