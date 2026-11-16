import numpy as np
import pandas as pd
import pytest

from xmercato.models import poisson


def _synthetic_league(n_teams=12, rounds=100, seed=0):
    """Many double round-robins generated from known parameters."""
    rng = np.random.default_rng(seed)
    teams = [f"T{k:02d}" for k in range(n_teams)]
    attack = rng.normal(0, 0.3, n_teams)
    defence = rng.normal(0, 0.3, n_teams)
    attack -= attack.mean()
    defence -= defence.mean()
    mu, home = 0.2, 0.25
    rows = []
    for _ in range(rounds):
        for i in range(n_teams):
            for j in range(n_teams):
                if i != j:
                    rows.append(
                        (
                            teams[i],
                            teams[j],
                            rng.poisson(np.exp(mu + home + attack[i] - defence[j])),
                            rng.poisson(np.exp(mu + attack[j] - defence[i])),
                        )
                    )
    df = pd.DataFrame(rows, columns=["home", "away", "home_goals", "away_goals"])
    return df, teams, attack, defence, mu, home


def test_recovers_known_parameters():
    df, teams, attack, defence, mu, home = _synthetic_league()
    fitted = poisson.fit(df, teams=teams, shrinkage=0.0)
    assert np.allclose(fitted.attack, attack, atol=0.07)
    assert np.allclose(fitted.defence, defence, atol=0.07)
    assert fitted.mu == pytest.approx(mu, abs=0.03)
    assert fitted.home_adv == pytest.approx(home, abs=0.03)


def test_shrinkage_pulls_towards_league_average():
    df, teams, *_ = _synthetic_league(rounds=1)
    loose = poisson.fit(df, teams=teams, shrinkage=0.0)
    tight = poisson.fit(df, teams=teams, shrinkage=50.0)
    assert np.abs(tight.attack).max() < np.abs(loose.attack).max()


def test_team_without_matches_gets_average_strength():
    df, teams, *_ = _synthetic_league(rounds=1)
    fitted = poisson.fit(df, teams=[*teams, "Promoted"], shrinkage=2.0)
    k = fitted.teams.index("Promoted")
    # Zero before centring, so equal to minus the mean shift: close to zero.
    assert abs(fitted.attack[k]) < 0.05
    assert abs(fitted.defence[k]) < 0.05


def test_unknown_team_raises():
    df, teams, *_ = _synthetic_league(rounds=1)
    with pytest.raises(ValueError, match="not in `teams`"):
        poisson.fit(df, teams=teams[:-1])


def test_scaled_multiplies_expected_goals():
    df, teams, *_ = _synthetic_league(rounds=2)
    base = poisson.fit(df, teams=teams)
    what_if = base.scaled(goals_for={"T00": 1.2}, goals_against={"T00": 0.5})
    home, away = base.expected_goals("T00", "T01")
    new_home, new_away = what_if.expected_goals("T00", "T01")
    assert new_home == pytest.approx(1.2 * home)
    assert new_away == pytest.approx(0.5 * away)
    # Matches without T00 are untouched, and the original object is not modified.
    assert what_if.expected_goals("T02", "T03") == base.expected_goals("T02", "T03")
    assert base.expected_goals("T00", "T01") == (home, away)
    with pytest.raises(ValueError, match="positive"):
        base.scaled(goals_for={"T00": 0.0})
