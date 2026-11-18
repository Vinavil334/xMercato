import numpy as np
import pandas as pd
import pytest

from xmercato.ingest import football_data_org as fdo
from xmercato.recommend import needs as nd
from xmercato.recommend import performance as perf
from xmercato.recommend.slots import SLOTS


def _history(seed=0):
    """Two seasons of a six-team league; in the second, team A stops scoring."""
    rng = np.random.default_rng(seed)
    teams = list("ABCDEF")
    rows, day = [], pd.Timestamp("2025-08-20")
    for season in (2025, 2026):
        day = pd.Timestamp(f"{season}-08-20")
        for _ in range(2):
            for h in teams:
                for a in teams:
                    if h == a:
                        continue
                    hg, ag = rng.poisson(1.5), rng.poisson(1.2)
                    if season == 2026 and h == "A":
                        hg = 0
                    if season == 2026 and a == "A":
                        ag = 0
                    rows.append((season, day, h, a, hg, ag))
                    day += pd.Timedelta(days=2)
    return pd.DataFrame(
        rows, columns=["season", "date", "home", "away", "home_goals", "away_goals"]
    )


def test_team_form_and_form_needs():
    teams = perf.team_form(_history(), 2026)
    a = teams.set_index("club").loc["A"]
    assert a["gol_fatti"] == 0 and a["gol_fatti_attesi"] > 5 and a["z_attacco"] < -2
    # The league's scoring level is corrected: on average teams score as expected.
    assert teams["gol_fatti"].sum() == pytest.approx(teams["gol_fatti_attesi"].sum(), rel=0.01)
    form = perf.form_needs(teams).set_index(["club", "slot"])
    assert form.loc[("A", "ATT"), "forma"] > form.loc[("A", "ALI"), "forma"] > 0
    assert form.loc[("A", "ATT"), "nota_forma"].startswith("attacco: 0 gol in 20 partite")
    assert form.loc[("A", "DC"), "forma"] == 0 or form.loc[("A", "DC"), "nota_forma"]


def test_form_raises_the_need():
    squad = pd.DataFrame(
        [{"club": "A", "slot": s, "giocatore": f"{s}{k}", "valore": 10.0, "eta": 26.0,
          "in_scadenza": False} for s in SLOTS for k in range(4)]
    )  # fmt: skip
    usage = pd.DataFrame([{"club": "A", "slot": s, "titolari": 1.0} for s in SLOTS])
    form = pd.DataFrame({"club": ["A"], "slot": ["ATT"], "forma": [1.0], "nota_forma": ["x"]})
    table = nd.needs(squad, usage, "gennaio", form=form).set_index("slot")
    assert table.loc["ATT", "rango"] == 1
    assert "sotto le attese in questa stagione: x" in table.loc["ATT", "motivo"]


def test_parse_scorers():
    payload = {
        "season": {"startDate": "2026-08-22"},
        "scorers": [
            {
                "player": {"id": 1, "name": "Randal Kolo Muani", "dateOfBirth": "1998-12-05",
                           "nationality": "France", "section": "Offence"},
                "team": {"name": "Juventus FC"},
                "playedMatches": 11, "goals": 1, "assists": 2, "penalties": None,
            }
        ],
    }  # fmt: skip
    got = fdo.parse_scorers(payload)
    assert got.iloc[0].to_dict() == {
        "season": 2026, "player_id": 1, "giocatore": "Randal Kolo Muani", "nascita": "1998-12-05",
        "nazionalita": "France", "ruolo": "Offence", "squadra": "Juventus FC", "partite": 11,
        "gol": 1, "assist": 2, "rigori": 0,
    }  # fmt: skip


def test_fit_rates_and_player_form():
    rng = np.random.default_rng(1)
    n = 400
    value = np.exp(rng.normal(2, 1, n))
    games = rng.integers(10, 38, n)
    rate = np.exp(-1.7 + 0.3 * np.log(value))
    ps = pd.DataFrame(
        {"competition_id": "IT1", "slot": "ATT", "partite": games, "valore_inizio": value * 1e6,
         "gol": rng.poisson(rate * games), "assist": 0}
    )  # fmt: skip
    rates = perf.fit_rates(ps)
    a, b = rates["ATT"]
    assert a == pytest.approx(-1.7, abs=0.2) and b == pytest.approx(0.3, abs=0.1)

    squad = pd.DataFrame(
        {"club": ["Juventus", "Juventus"], "slot": ["ATT", "ATT"], "valore": [40.0, 5.0],
         "giocatore": ["Randal Kolo Muani", "Arkadiusz Milik"]}
    )  # fmt: skip
    usage = pd.DataFrame({"club": ["Juventus"], "slot": ["ATT"], "titolari": [1.0]})
    scorers = pd.DataFrame(
        {"giocatore": ["R. Kolo Muani"], "squadra": ["Juventus"], "partite": [11], "gol": [1],
         "assist": [2]}
    )  # fmt: skip
    got = perf.player_form(squad, usage, scorers, rates, pd.Series({"Juventus": 11}))
    row = got.iloc[0]
    assert len(got) == 1 and row["giocatore"] == "Randal Kolo Muani" and row["nei_marcatori"]
    assert row["gol_assist"] == 3 and row["attesi"] > 4 and row["z"] < -1
    teams = pd.DataFrame(
        {"club": ["Juventus"], "partite": [11], "gol_fatti": [15], "gol_fatti_attesi": [15.0],
         "gol_subiti": [10], "gol_subiti_attesi": [10.0], "z_attacco": [0.0], "z_difesa": [0.0]}
    )  # fmt: skip
    form = perf.form_needs(teams, got).set_index("slot")
    assert form.loc["ATT", "forma"] > 0
    assert "Randal Kolo Muani: 3 tra gol e assist in 11 partite" in form.loc["ATT", "nota_forma"]


def test_unlisted_starter_counts_as_no_goals():
    rates = {"ATT": (-1.7, 0.3)}
    squad = pd.DataFrame({"club": ["A"], "slot": ["ATT"], "valore": [30.0], "giocatore": ["X Y"]})
    usage = pd.DataFrame({"club": ["A"], "slot": ["ATT"], "titolari": [1.0]})
    scorers = pd.DataFrame(columns=["giocatore", "squadra", "partite", "gol", "assist"])
    got = perf.player_form(squad, usage, scorers, rates, pd.Series({"A": 12}))
    assert not got.iloc[0]["nei_marcatori"] and got.iloc[0]["gol_assist"] == 0


def test_form_ignores_slots_the_club_does_not_use():
    squad = pd.DataFrame(
        [{"club": "A", "slot": s, "giocatore": f"{s}{k}", "valore": 10.0, "eta": 26.0,
          "in_scadenza": False} for s in SLOTS for k in range(4)]
    )  # fmt: skip
    usage = pd.DataFrame([{"club": "A", "slot": s, "titolari": 0.0 if s == "ALI" else 1.0}
                          for s in SLOTS])  # fmt: skip
    form = pd.DataFrame({"club": ["A"], "slot": ["ALI"], "forma": [1.0], "nota_forma": ["x"]})
    row = nd.needs(squad, usage, "gennaio", form=form).set_index("slot").loc["ALI"]
    assert row["punteggio"] == 0 and "sotto le attese" not in row["motivo"]
