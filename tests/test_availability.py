import pandas as pd
import pytest

from xmercato.recommend import availability
from xmercato.recommend import needs as nd
from xmercato.recommend import performance as perf
from xmercato.recommend.slots import SLOTS

TODAY = pd.Timestamp("2026-11-19")
CLOSE = pd.Timestamp("2027-02-02")


def _squad():
    rows = [{"club": "Juventus", "slot": s, "giocatore": f"{s} {k}", "valore": 10.0, "eta": 26.0,
             "in_scadenza": False} for s in SLOTS for k in range(3)]  # fmt: skip
    rows += [
        {"club": "Juventus", "slot": "CC", "giocatore": "Manuel Locatelli", "valore": 30.0,
         "eta": 28.0, "in_scadenza": False},
        {"club": "Juventus", "slot": "ALI", "giocatore": "Kenan Yıldız", "valore": 80.0,
         "eta": 21.0, "in_scadenza": False},
    ]  # fmt: skip
    return pd.DataFrame(rows)


def _absences(tmp_path, rows):
    path = tmp_path / "indisponibili.csv"
    pd.DataFrame(rows, columns=availability.COLUMNS).to_csv(path, index=False)
    return availability.read(path)


def test_long_absence_leaves_the_squad_short_one_does_not(tmp_path):
    absences = _absences(tmp_path, [
        ["Juventus", "Locatelli", "menisco", "nel 2027", "2027-02-15", "x", "2026-11-18"],
        ["Juventus", "Kenan Yildiz", "piede", "dicembre", "2026-12-15", "x", "2026-11-18"],
        ["Juventus", "ALI 0", "vecchio infortunio", "ottobre", "2026-10-15", "x", "2026-10-01"],
    ])  # fmt: skip
    squad = _squad()
    available, notes, injured = availability.apply(squad, absences, TODAY, CLOSE)
    assert "Manuel Locatelli" not in set(available["giocatore"])
    assert "Kenan Yıldız" in set(available["giocatore"])  # back before the window closes
    names = set(squad.loc[list(injured), "giocatore"])
    assert names == {"Manuel Locatelli", "Kenan Yıldız"}  # the October one is over
    assert (
        notes.iloc[0]["slot"] == "CC"
        and "Manuel Locatelli (menisco" in notes.iloc[0]["nota_assenze"]
    )
    usage = pd.DataFrame([{"club": "Juventus", "slot": s, "titolari": 1.0} for s in SLOTS])
    row = nd.needs(available, usage, "gennaio", absences=notes).set_index("slot").loc["CC"]
    assert "assenti a lungo: Manuel Locatelli" in row["motivo"]


def test_unknown_names_are_an_error(tmp_path):
    absences = _absences(tmp_path, [
        ["Juventus", "Nessuno Qui", "x", "dicembre", "2026-12-15", "x", "2026-11-18"],
    ])  # fmt: skip
    with pytest.raises(ValueError, match="Nessuno Qui"):
        availability.apply(_squad(), absences, TODAY, CLOSE)


def test_injured_forwards_are_not_judged():
    squad = pd.DataFrame({"club": ["A"], "slot": ["ATT"], "valore": [30.0], "giocatore": ["X Y"]})
    usage = pd.DataFrame({"club": ["A"], "slot": ["ATT"], "titolari": [1.0]})
    scorers = pd.DataFrame(columns=["giocatore", "squadra", "partite", "gol", "assist"])
    rates = {"ATT": (-1.7, 0.3)}
    games = pd.Series({"A": 12})
    assert len(perf.player_form(squad, usage, scorers, rates, games)) == 1
    assert perf.player_form(squad, usage, scorers, rates, games, injured={0}).empty


def test_the_real_list_matches_the_squads():
    squads = pd.read_csv("rose/serie_a_2026_27.csv")
    absences = availability.read("rose/indisponibili_2026_27.csv")
    assert availability.match(squads, absences).notna().all()
