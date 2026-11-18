"""Smoke tests for the Streamlit app, run headless with Streamlit's own test harness."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit")
import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from xmercato.ingest import football_data  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")
SAMPLE = "2025/26 (completa, inclusa nell'app)"


def _offline(source):
    if str(source).startswith("http"):
        raise ConnectionError("no network in tests")
    return ORIGINAL_LOAD(source)


ORIGINAL_LOAD = football_data.load_results


@pytest.fixture
def app(monkeypatch):
    # The app downloads seasons from football-data.co.uk: in tests every download fails,
    # so the app falls back to the bundled season and to the one-season model.
    monkeypatch.setattr(football_data, "load_results", _offline)
    st.cache_data.clear()
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    # Work on the bundled season so the tests never touch the network.
    at.sidebar.radio[0].set_value(SAMPLE).run()
    assert not at.exception
    return at


def _table(at, title):
    """The league table (it has a "PG" column) or the table of changes (it does not)."""
    assert title in [h.value for h in at.subheader]
    frames = [frame.value for frame in at.dataframe]
    wanted = title == "Classifica finale prevista"
    return next(
        f
        for f in frames
        if ("PG" in f.columns) == wanted and "Squadra" in [*f.columns, f.index.name]
    )


def test_loads_and_shows_twenty_teams(app):
    table = _table(app, "Classifica finale prevista")
    assert len(table) == 20
    assert table["Scudetto"].sum() == pytest.approx(100, abs=0.01)
    assert "Cosa cambia" not in [h.value for h in app.subheader]


def test_strength_scenario_shows_changes(app):
    before = _table(app, "Classifica finale prevista").set_index("Squadra")
    app.multiselect(key="mod_teams").set_value(["Roma"]).run()
    app.slider(key="gf_Roma").set_value(30).run()
    assert not app.exception
    after = _table(app, "Classifica finale prevista").set_index("Squadra")
    assert after.loc["Roma", "Punti attesi"] > before.loc["Roma", "Punti attesi"]
    changes = _table(app, "Cosa cambia")
    assert changes.index[0] == "Roma"
    assert changes.loc["Roma", "Punti attesi"] > 0


def test_fixed_result_and_reset(app):
    # The selectbox shows "Home – Away" but holds the (home, away) pair.
    pair = tuple(app.selectbox[0].options[0].split(" – "))
    app.selectbox[0].set_value(pair)
    app.number_input[1].set_value(4)
    app.button[1].click().run()
    assert not app.exception
    assert app.session_state["fixed"] == {pair: (0, 4)}
    assert "Cosa cambia" in [h.value for h in app.subheader]

    app.button[0].click().run()  # "Azzera"
    assert not app.exception
    assert app.session_state["fixed"] == {}
    assert "Cosa cambia" not in [h.value for h in app.subheader]


def test_uses_the_previous_seasons_when_available(monkeypatch):
    # Pretend the two previous seasons are online (the bundled one stands in for both).
    monkeypatch.setattr(
        football_data, "load_results", lambda source: ORIGINAL_LOAD(football_data.SAMPLE_SEASON)
    )
    st.cache_data.clear()
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.sidebar.radio[0].set_value(SAMPLE).run()
    assert not at.exception
    assert not [w.value for w in at.warning if "stagioni precedenti" in w.value]
    assert len(_table(at, "Classifica finale prevista")) == 20


def test_falls_back_to_one_season(app):
    assert [w.value for w in app.warning if "stagioni precedenti" in w.value]
