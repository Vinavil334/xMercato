import numpy as np
import pandas as pd
import pytest

from xmercato.evaluation import needs_backtest as nb
from xmercato.recommend import candidates as cand
from xmercato.recommend import market
from xmercato.recommend import needs as nd
from xmercato.recommend.slots import SLOTS, best_slot


def test_best_slot_falls_back():
    played = pd.Series(["Left Midfield", None, None])
    listed = pd.Series(["Left-Back", "Second Striker", None])
    ruolo = pd.Series(["DIF", "ATT", "POR"])
    assert list(best_slot(played, listed, ruolo=ruolo)) == ["TS", "TRQ", "POR"]


def test_required():
    assert nd.required(1.0, "POR") == 3
    assert nd.required(2.0, "DC") == 4
    assert nd.required(3.0, "DC") == 5
    assert nd.required(0.1, "TRQ") == 0


def _squad(club, counts, value=10.0):
    rows = []
    for slot, n in counts.items():
        rows += [{"club": club, "slot": slot, "giocatore": f"{club}{slot}{k}", "valore": value,
                  "eta": 26.0, "in_scadenza": False} for k in range(n)]  # fmt: skip
    return pd.DataFrame(rows)


FULL = {"POR": 3, "DC": 4, "TD": 2, "TS": 2, "CC": 5, "TRQ": 0, "ALI": 4, "ATT": 3}
USAGE = {"POR": 1, "DC": 2, "TD": 1, "TS": 1, "CC": 3, "TRQ": 0, "ALI": 2, "ATT": 1}


def _usage(clubs):
    return pd.DataFrame(
        [{"club": c, "slot": s, "titolari": float(USAGE[s])} for c in clubs for s in SLOTS]
    )


def test_needs_depth_and_quality():
    thin = _squad("A", {**FULL, "TS": 1})
    weak = _squad("B", FULL)
    weak.loc[weak["slot"] == "POR", "valore"] = 1.0  # goalkeepers worth much less than usual
    ok = _squad("C", FULL)
    table = nd.needs(pd.concat([thin, weak, ok]), _usage("ABC"), "gennaio")
    first = table[table["rango"] == 1].set_index("club")["slot"]
    assert first["A"] == "TS" and first["B"] == "POR"
    row = table.set_index(["club", "slot"]).loc[("A", "TS")]
    assert row["mancano"] == 1 and row["motivo"].startswith("1 giocatore per 2")
    assert table.set_index(["club", "slot"]).loc[("C", "TS"), "motivo"] == "reparto coperto"


def test_neighbours_cover_half():
    # No trequartista, but two spare central midfielders: half a player each.
    squad = _squad("A", {**FULL, "CC": 7})
    usage = _usage("A")
    usage.loc[usage["slot"] == "TRQ", "titolari"] = 1.0
    row = nd.needs(squad, usage, "gennaio").set_index("slot").loc["TRQ"]
    assert row["servono"] == 2 and row["mancano"] == 1


def test_usage_rescales_and_fills_missing_clubs():
    ps = pd.DataFrame(
        {
            "club_id": [1, 1, 1],
            "season": [2025] * 3,
            "slot": ["POR", "DC", "ATT"],
            "titolare": [38, 76, 38],
            "partite_club": [38] * 3,
        }
    )
    u = nd.usage(ps, {1: "A", 2: "B"}, 2025).pivot(index="club", columns="slot", values="titolari")
    assert u.loc["A"].sum() == pytest.approx(11)
    assert (u.loc["B"] == u.loc["A"]).all()  # no lineups: league average


def test_arrivals_skip_loan_returns_and_youth():
    t = pd.DataFrame(
        {
            "player_id": [1, 1, 2, 3],
            "transfer_date": ["2024-08-01", "2026-01-10", "2026-01-15", "2026-01-20"],
            "from_club_id": [10, 20, 30, 40],
            "to_club_id": [20, 10, 10, 10],
            "from_club_name": ["A", "B", "Club U19", "C"],
            "to_club_name": ["B", "A", "A", "A"],
            "player_name": ["x", "x", "y", "z"],
        }
    )
    got = nb.arrivals(t, [10], 2025, "gennaio")
    assert list(got["player_id"]) == [3]


def test_relations_and_features():
    t = pd.DataFrame(
        {"transfer_date": ["2025-01-01", "2025-07-01", "2010-01-01"],
         "from_club_id": [5, 9, 5], "to_club_id": [9, 5, 9]}
    )  # fmt: skip
    deals = cand.relations(t, pd.Timestamp("2026-01-01"))
    assert deals[(5, 9)] == 2
    pool = pd.DataFrame(
        {
            "club_id": [5, 7],
            "competition_id": ["IT1", "GB1"],
            "valore": [10.0, 2.5],
            "nascita": pd.to_datetime(["2000-01-01", None]),
            "minuti_quota": [0.5, 0.9],
            "cittadinanza": ["Italy", "England"],
            "esperienza_a": [1.0, 0.0],
            "forza_club": [10.0, np.nan],
            "tendenza": [0.0, np.nan],
        }
    )
    x = cand.features(pool, 9, 10.0, deals, pd.Timestamp("2026-01-01"))
    assert x["rel_valore"].iloc[0] == pytest.approx(0)
    assert x["eta"].iloc[1] == 25  # unknown birth date
    assert x["rapporti"].iloc[0] == pytest.approx(np.log(3))
    assert x["camp_Premier League"].tolist() == [0.0, 1.0]
    assert set(cand.FEATURES) <= set(x.columns)


def test_model_learns_price_and_corrects_for_sampling():
    rng = np.random.default_rng(0)
    n = 4000
    x = pd.DataFrame(0.0, index=range(n), columns=cand.FEATURES)
    x["rel_valore"] = rng.normal(size=n)
    x["rel_valore_2"] = x["rel_valore"] ** 2
    y = (rng.random(n) < 1 / (1 + np.exp(-(-1 - 2 * x["rel_valore_2"])))).astype(float)
    model = cand.PlausibilityModel().fit(x, y.to_numpy(), sampled_share=0.1)
    assert model.coefficients()["rel_valore_2"] < 0
    near, far = model.probability(x.iloc[[0]].assign(rel_valore=0, rel_valore_2=0)), \
        model.probability(x.iloc[[0]].assign(rel_valore=2, rel_valore_2=4))  # fmt: skip
    assert near[0] > far[0]
    # Keeping one non-signing in ten makes the corrected chances smaller.
    assert model.probability(x).mean() < y.mean()


def test_expected_role():
    roles = market.expected_role(pd.Series([12.0, 6.0, 2.0]), 10.0)
    assert list(roles) == ["titolare", "rotazione", "riserva"]
