import numpy as np
import pandas as pd
import pytest

from xmercato.evaluation import lineups_backtest as lb
from xmercato.models import lineups, poisson
from xmercato.recommend import availability


def _squad():
    return pd.DataFrame(
        {"club": ["A"] * 4 + ["B"] * 2,
         "giocatore": ["Star Uno", "Riserva Due", "Portiere Tre", "Altro Quattro", "Bi Uno",
                       "Bi Due"],
         "slot": ["ATT", "ATT", "POR", "CC", "ATT", "POR"],
         "valore": [40.0, 10.0, 10.0, 20.0, 5.0, 5.0]}
    )  # fmt: skip


def _usage():
    return pd.DataFrame(
        {"club": ["A", "A", "A", "B", "B"], "slot": ["ATT", "POR", "CC", "ATT", "POR"],
         "titolari": [1.0, 1.0, 1.0, 1.0, 1.0]}
    )  # fmt: skip


def test_eleven_value():
    value = lineups.eleven_value(_squad(), _usage())
    assert value["A"] == pytest.approx(70.0) and value["B"] == pytest.approx(10.0)


def test_absence_effect(tmp_path):
    path = tmp_path / "a.csv"
    pd.DataFrame(
        [["A", "Star Uno", "x", "fine stagione", "2027-06-30", "x", "2026-11-18"]],
        columns=availability.COLUMNS,
    ).to_csv(path, index=False)
    absences = availability.read(path)
    start, end = pd.Timestamp("2026-11-20"), pd.Timestamp("2027-05-31")
    effect = lineups.absence_effect(_squad(), _usage(), absences, start, end).set_index("club")
    # Out for the whole season: the eleven goes from 70 to 40 (the backup comes in).
    assert effect.loc["A", "calo"] == pytest.approx(np.log(40 / 70))
    assert effect.loc["A", "gol_fatti"] < 1 < effect.loc["A", "gol_subiti"]
    assert effect.loc["A", "assenti"] == "Star Uno"
    assert effect.loc["B", "calo"] == 0 and effect.loc["B", "gol_fatti"] == 1
    # Back halfway: about half the loss.
    absences["rientro_stimato"] = start + (end - start) / 2
    half = lineups.absence_effect(_squad(), _usage(), absences, start, end).set_index("club")
    assert half.loc["A", "calo"] == pytest.approx(np.log(40 / 70) / 2, rel=0.1)


def test_implied_rates_round_trip():
    lam_h, lam_a = np.array([1.6, 0.9]), np.array([1.1, 1.4])
    p = poisson.outcome_probabilities(lam_h, lam_a)
    got = lb.implied_rates(p[:, 0], p[:, 2])
    assert got[:, 0] == pytest.approx(lam_h, rel=1e-3) and got[:, 1] == pytest.approx(
        lam_a, rel=1e-3
    )


def test_estimate_recovers_the_effect():
    rng = np.random.default_rng(0)
    n = 2000
    games = pd.DataFrame({"delta_h": rng.normal(0, 0.2, n), "delta_a": rng.normal(0, 0.2, n),
                          "lam_h": 1.5, "lam_a": 1.1})  # fmt: skip
    games["book_h"] = games["lam_h"] * np.exp(0.1 * games["delta_h"] - 0.13 * games["delta_a"])
    games["book_a"] = games["lam_a"] * np.exp(0.1 * games["delta_a"] - 0.13 * games["delta_h"])
    effect, margin = lb.estimate(games)
    assert effect.own == pytest.approx(0.1, abs=1e-6)
    assert effect.opponent == pytest.approx(-0.13, abs=1e-6)


def test_deltas():
    elevens = pd.DataFrame(
        {"game_id": range(5), "date": [f"2025-09-0{k + 1}" for k in range(5)], "season": 2025,
         "club_id": 1, "starters": 11, "value_attack": [50, 50, 50, 50, 25],
         "value_defence": [50, 50, 50, 50, 25]}
    )  # fmt: skip
    d = lb.deltas(elevens)
    assert list(d["game_id"]) == [3, 4]  # three earlier games needed
    assert d["delta"].iloc[-1] == pytest.approx(np.log(0.5))
