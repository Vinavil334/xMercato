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


def test_injured_forwards_are_not_judged_and_out_ones_are_replaced():
    squad = pd.DataFrame(
        {"club": ["A", "A"], "slot": ["ATT", "ATT"], "valore": [30.0, 10.0],
         "giocatore": ["X Y", "Z W"]}
    )  # fmt: skip
    usage = pd.DataFrame({"club": ["A"], "slot": ["ATT"], "titolari": [1.0]})
    scorers = pd.DataFrame(columns=["giocatore", "squadra", "partite", "gol", "assist"])
    stats = perf.forward_stats(squad, scorers, {"ATT": (-1.7, 0.3)}, pd.Series({"A": 12}))
    assert list(perf.player_form(stats, usage)["giocatore"]) == ["X Y"]
    assert perf.player_form(stats, usage, injured={("A", "X Y")}).empty
    assert list(perf.player_form(stats, usage, out={("A", "X Y")})["giocatore"]) == ["Z W"]


def test_candidates_out_for_the_window(tmp_path):
    absences = _absences(tmp_path, [
        ["Juventus", "Locatelli", "menisco", "nel 2027", "2027-02-15", "x", "2026-11-18"],
        ["Juventus", "Kenan Yildiz", "piede", "dicembre", "2026-12-15", "x", "2026-11-18"],
    ])  # fmt: skip
    candidates = pd.DataFrame(
        {"giocatore": ["Manuel Locatelli", "Kenan Yıldız", "Manuel Locatelli"],
         "club_attuale": ["Juventus", "Juventus", "Sassuolo"]}
    )  # fmt: skip
    note, out = availability.candidate_status(candidates, absences, TODAY, CLOSE)
    assert list(out) == [True, False, False]
    assert note[1].startswith("infortunato (piede") and note[2] == ""


def test_csv_round_trip(tmp_path):
    rows = [["Juventus", "Locatelli", "menisco", "nel 2027", "2027-02-15", "x", "2026-11-18"],
            ["Inter", "Bonny", "flessori", "dicembre", "", "y", "2026-11-18"]]  # fmt: skip
    absences = _absences(tmp_path, rows)
    text = availability.to_csv(absences)
    assert text.splitlines()[1].startswith("Inter,Bonny,flessori,dicembre,,y,2026-11-18")
    path = tmp_path / "again.csv"
    path.write_text(text)
    assert availability.to_csv(availability.read(path)) == text


def test_the_real_list_matches_the_squads():
    squads = pd.read_csv("rose/serie_a_2026_27.csv")
    absences = availability.read("rose/indisponibili_2026_27.csv")
    assert availability.match(squads, absences).notna().all()
