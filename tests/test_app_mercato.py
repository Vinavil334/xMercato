"""Smoke tests for the market page."""

from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MAIN = str(ROOT / "app" / "streamlit_app.py")
PAGE = str(ROOT / "app" / "mercato.py")


@pytest.fixture
def page():
    at = AppTest.from_file(PAGE, default_timeout=60).run()
    assert not at.exception
    return at


def _tables(page):
    """The page's tables by their first column: needs, editor, squad, candidates."""
    return {tuple(d.value.columns[:2]): d.value for d in page.dataframe}


def test_needs_squad_and_candidates(page):
    tables = _tables(page)
    needs = tables[("Urgenza", "Perché")]
    squad = tables[("Giocatore", "Ruolo")]
    candidates = tables[("Giocatore", "Probabilità")]
    assert len(needs) == 8  # one row per slot
    assert len(squad) > 20 and set(squad["Stato"]) <= {
        "disponibile",
        "infortunato",
        "fuori per la finestra",
    }
    assert 0 < len(candidates) <= 15
    assert candidates["Probabilità"].is_monotonic_decreasing


def test_an_added_injury_changes_the_needs(page):
    key = "assenze_gennaio_2027"
    before = _tables(page)[("Urgenza", "Perché")]
    absences = page.session_state[key]
    extra = pd.DataFrame(
        [{"club": "Atalanta", "giocatore": "Marco Carnesecchi", "problema": "test",
          "rientro": "marzo", "rientro_stimato": pd.Timestamp("2027-03-15"), "fonte": "x",
          "aggiornato": pd.Timestamp("2026-11-19")}]
    )  # fmt: skip
    page.session_state[key] = pd.concat([absences, extra], ignore_index=True)
    page.run()
    assert not page.exception
    after = _tables(page)[("Urgenza", "Perché")]
    assert "Marco Carnesecchi" in after.loc["Portiere", "Perché"]
    assert after.loc["Portiere", "Urgenza"] > before.loc["Portiere", "Urgenza"]
    assert page.info  # "Elenco modificato"


def test_other_club_and_slot(page):
    page.selectbox(key="club").set_value("Napoli").run()
    assert not page.exception
    slot_box = page.selectbox(key="slot_Napoli")
    last = slot_box.options[-1]
    slot_box.select_index(len(slot_box.options) - 1).run()
    assert not page.exception
    assert page.selectbox(key="slot_Napoli").options[-1] == last


def test_filters_can_empty_the_list(page):
    page.slider(key="max_age").set_value(17).run()
    assert not page.exception
    assert any(i.value.startswith("Nessun candidato") for i in page.info)


def test_navigation_to_the_market_page():
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    at.switch_page("mercato.py").run()
    assert not at.exception
    assert at.title[0].value == "Mercato"


def test_injured_players_are_listed(page):
    if pd.Timestamp.today() > pd.Timestamp("2027-02-15"):
        pytest.skip("Locatelli's expected return has passed")
    page.selectbox(key="club").set_value("Juventus").run()
    editor = _tables(page)[("Giocatore", "Problema")]
    assert "Manuel Locatelli" in set(editor["Giocatore"])
    squad = _tables(page)[("Giocatore", "Ruolo")].set_index("Giocatore")
    assert squad.loc["Manuel Locatelli", "Stato"] == "fuori per la finestra"
