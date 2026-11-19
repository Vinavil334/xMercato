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


def test_needs_and_candidates(page):
    assert [h.value for h in page.subheader][1] == "Candidati"
    needs, candidates = page.dataframe[0].value, page.dataframe[-1].value
    assert len(needs) == 8  # one row per slot
    assert 0 < len(candidates) <= 15
    assert candidates["Probabilità"].is_monotonic_decreasing


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
    assert page.info  # nobody aged 17 or less among the top candidates


def test_navigation_to_the_market_page():
    at = AppTest.from_file(MAIN, default_timeout=60).run()
    at.switch_page("mercato.py").run()
    assert not at.exception
    assert at.title[0].value == "Mercato"


def test_injured_players_are_listed(page):
    if pd.Timestamp.today() > pd.Timestamp("2027-02-15"):
        pytest.skip("Locatelli's expected return has passed")
    page.selectbox(key="club").set_value("Juventus").run()
    tables = [d.value for d in page.dataframe]
    injured = [t for t in tables if "Rientro previsto" in t.columns]
    assert injured and "Manuel Locatelli" in set(injured[0]["Giocatore"])
