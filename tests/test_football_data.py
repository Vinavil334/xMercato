from pathlib import Path

import pandas as pd
import pytest

from xmercato.ingest import football_data

FIXTURE = Path(__file__).parent / "data" / "serie_a_2025_26.csv"


def test_loads_full_season():
    df = football_data.load_results(FIXTURE)
    assert list(df.columns) == ["date", "home", "away", "home_goals", "away_goals"]
    assert len(df) == 380
    assert df["home"].nunique() == 20
    assert df["date"].is_monotonic_increasing
    assert df["date"].min() == pd.Timestamp("2025-08-23")


def test_original_site_date_format_and_unplayed_rows(tmp_path):
    path = tmp_path / "I1.csv"
    path.write_text(
        "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n"
        "I1,24/08/2025,19:45,Roma,Bologna,1,0,H\n"
        "I1,23/08/2025,17:30,Genoa,Lecce,0,0,D\n"
        "I1,30/08/2025,19:45,Lecce,Milan,,,\n"
    )
    df = football_data.load_results(path)
    assert len(df) == 2
    assert df.loc[0, "home"] == "Genoa"
    assert df.loc[1, "date"] == pd.Timestamp("2025-08-24")


def test_rejects_other_files(tmp_path):
    path = tmp_path / "other.csv"
    path.write_text("a,b\n1,2\n")
    with pytest.raises(ValueError, match="missing columns"):
        football_data.load_results(path)


def test_season_url():
    assert football_data.serie_a_url(2025).endswith("/2526/I1.csv")
    assert football_data.serie_a_url(1999).endswith("/9900/I1.csv")
