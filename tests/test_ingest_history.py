import json

import pandas as pd
import pytest

from xmercato.ingest import football_data, history, teams, understat


def _event(i, date, home, away, hg, ag, hxg, axg, played=True):
    return {
        "id": str(i), "isResult": played, "datetime": f"{date} 20:45:00",
        "h": {"id": "1", "title": home, "short_title": home[:3].upper()},
        "a": {"id": "2", "title": away, "short_title": away[:3].upper()},
        "goals": {"h": str(hg) if played else None, "a": str(ag) if played else None},
        "xG": {"h": str(hxg) if played else None, "a": str(axg) if played else None},
    }  # fmt: skip


EVENTS = [
    _event(2, "2025-08-24", "Inter", "Parma Calcio 1913", 5, 0, 2.91, 0.34),
    _event(1, "2025-08-23", "AC Milan", "Hellas Verona", 1, 1, 1.20, 0.80),
    _event(3, "2025-08-30", "Parma Calcio 1913", "AC Milan", 0, 0, 0, 0, played=False),
]


def test_parse_events_keeps_played_matches():
    df = understat.parse_events(EVENTS)
    assert list(df["understat_id"]) == [1, 2]  # sorted by date
    row = df.iloc[1]
    assert (row["home"], row["away"]) == ("Inter", "Parma Calcio 1913")
    assert (row["home_goals"], row["home_xg"]) == (5, 2.91)
    assert row["date"] == pd.Timestamp("2025-08-24")


def test_parse_old_style_league_page():
    payload = json.dumps(EVENTS[:1]).replace('"', "\\x22")
    html = f"<script>var datesData = JSON.parse('{payload}');</script>"
    events = understat.parse_league_page(html)
    assert events[0]["h"]["title"] == "Inter"
    with pytest.raises(ValueError, match="datesData"):
        understat.parse_league_page("<html></html>")


@pytest.mark.parametrize(
    ("source", "canonical"),
    [("AC Milan", "Milan"), ("Parma Calcio 1913", "Parma"), ("Hellas Verona", "Verona"),
     ("Inter", "Inter"), ("SPAL 2013", "Spal"), ("Atalanta", "Atalanta")],
)  # fmt: skip
def test_team_names(source, canonical):
    clubs = {"Milan", "Parma", "Verona", "Inter", "Spal", "Atalanta"}
    assert teams.map_names({source}, clubs)[source] == canonical


def test_unknown_team_name_raises():
    with pytest.raises(ValueError, match="Could not map"):
        teams.map_names({"Real Madrid"}, {"Milan", "Inter"})


def _fd_file(tmp_path):
    path = tmp_path / "I1.csv"
    path.write_text(
        "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,B365H,B365D,B365A,PSCH,PSCD,PSCA\n"
        "I1,23/08/2025,Milan,Verona,1,1,1.40,4.5,8.0,1.45,4.6,7.5\n"
        "I1,24/08/2025,Inter,Parma,5,0,1.25,6.0,12.0,,,\n"
    )
    return path


def test_odds_prefer_closing_then_fall_back(tmp_path):
    df = football_data.load_matches(_fd_file(tmp_path))
    milan, inter = df.iloc[0], df.iloc[1]
    assert (milan["odds_home"], milan["odds_source"]) == (1.45, "PSC")
    assert (inter["odds_home"], inter["odds_source"]) == (1.25, "B365")


def test_combine_one_season(tmp_path):
    results = football_data.load_matches(_fd_file(tmp_path))
    xg = understat.parse_events(EVENTS)
    df = history.combine(results, xg, 2025)
    assert list(df.columns) == history.COLUMNS
    inter = df[df["home"] == "Inter"].iloc[0]
    assert (inter["away"], inter["home_xg"], inter["away_xg"]) == ("Parma", 2.91, 0.34)
    assert (df["season"] == 2025).all()


def test_build_uses_the_loaders(tmp_path):
    results = football_data.load_matches(_fd_file(tmp_path))
    df = history.build(
        [2025], load_results=lambda s: results, load_xg=lambda s: understat.parse_events(EVENTS)
    )
    assert len(df) == 2
    path = tmp_path / "history.csv"
    df.to_csv(path, index=False)
    assert len(history.read(path)) == 2
