import pandas as pd
import pytest

from xmercato.ingest import football_data, history, teams, understat


def _shots():
    """Three shots in one match and one in another, as in the Understat archive."""
    rows = [
        # match_id, side, xG
        (1, "h", 0.40), (1, "h", 0.35), (1, "a", 0.10),
        (2, "a", 0.80),
    ]  # fmt: skip
    info = {
        1: ("2025-08-23 20:45:00", "AC Milan", "Hellas Verona", 1, 1),
        2: ("2025-08-24 18:30:00", "Inter", "Parma Calcio 1913", 5, 0),
    }
    return pd.DataFrame(
        [
            {
                "match_id": m, "h_a": side, "xG": xg, "season": 2025, "date": info[m][0],
                "home_team": info[m][1], "away_team": info[m][2],
                "home_goals": info[m][3], "away_goals": info[m][4],
            }
            for m, side, xg in rows
        ]
    )  # fmt: skip


def test_match_xg_sums_shots():
    df = understat.match_xg(_shots())
    milan = df.iloc[0]
    assert (milan["home"], milan["home_xg"], milan["away_xg"]) == ("AC Milan", 0.75, 0.10)
    inter = df.iloc[1]
    assert (inter["home_xg"], inter["away_xg"]) == (0.0, 0.8)  # no home shots recorded
    assert inter["date"] == pd.Timestamp("2025-08-24")


def test_match_xg_rejects_other_tables():
    with pytest.raises(ValueError, match="missing"):
        understat.match_xg(pd.DataFrame({"a": [1]}))


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
        "I1,30/08/2025,Parma,Milan,0,2,4.0,3.5,1.9,,,\n"
    )
    return path


def test_odds_prefer_closing_then_fall_back(tmp_path):
    df = football_data.load_matches(_fd_file(tmp_path))
    milan, inter = df.iloc[0], df.iloc[1]
    assert (milan["odds_home"], milan["odds_source"]) == (1.45, "PSC")
    assert (inter["odds_home"], inter["odds_source"]) == (1.25, "B365")


def test_combine_partial_xg(tmp_path):
    results = football_data.load_matches(_fd_file(tmp_path))
    df = history.combine(results, understat.match_xg(_shots()), 2025)
    assert list(df.columns) == history.COLUMNS
    inter = df[df["home"] == "Inter"].iloc[0]
    assert (inter["away"], inter["away_xg"]) == ("Parma", 0.8)
    assert df["home_xg"].notna().sum() == 2  # the third match has no xG in the archive


def test_combine_rejects_inconsistent_dates(tmp_path):
    results = football_data.load_matches(_fd_file(tmp_path))
    xg = understat.match_xg(_shots())
    xg.loc[0, "date"] = pd.Timestamp("2025-10-01")
    with pytest.raises(ValueError, match="dates differ"):
        history.combine(results, xg, 2025)


def test_build_with_and_without_xg(tmp_path):
    results = football_data.load_matches(_fd_file(tmp_path))
    xg = understat.match_xg(_shots())
    df = history.build([2025, 2026], load_results=lambda s: results, xg=xg)
    assert df.groupby("season")["home_xg"].count().to_dict() == {2025: 2, 2026: 0}
    path = tmp_path / "history.csv"
    df.to_csv(path, index=False)
    assert len(history.read(path)) == 6


def test_match_xg_reads_the_newer_side_column():
    shots = _shots().assign(home_away=lambda d: d["h_a"].map({"h": "home", "a": "away"}))
    shots["h_a"] = None
    df = understat.match_xg(shots)
    assert (df.iloc[0]["home_xg"], df.iloc[0]["away_xg"]) == (0.75, 0.10)
