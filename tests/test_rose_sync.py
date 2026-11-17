import pandas as pd
import pytest

from xmercato import rose, rose_sync


def test_normalise():
    assert rose_sync.normalise("Hakan Çalhanoğlu") == "hakan calhanoglu"
    assert rose_sync.normalise("Ruben Loftus-Cheek") == "ruben loftus cheek"
    assert rose_sync.normalise("Piotr Zieliński") == rose_sync.normalise("Piotr Zielinski")


@pytest.mark.parametrize(
    ("a", "b", "same"),
    [
        ("Pio Esposito", "Francesco Pio Esposito", True),
        ("Alphadjo Cisse", "Alphadjo Cissè", True),
        ("Piotr Zieliński", "Piotr Zielinski", True),
        ("Mario Gila", "Mario Rui", False),
        ("Lautaro Martínez", "Josep Martínez", False),
        ("Esposito", "Pio Esposito", False),  # a surname alone is not enough
    ],
)
def test_similarity(a, b, same):
    assert (rose_sync.similarity(a, b) >= rose_sync.SAME_NAME) is same


def _squads():
    rows = [
        # club, name, tm_id, born, role, arrival, contract, value
        ("Inter", "Lautaro Martínez", 1, "1997-08-22", "ATT", "2018-07-04", "2029-06-30", 85.0),
        ("Inter", "Yann Sommer", 2, "1988-12-17", "POR", "2023-08-19", "2026-06-30", 2.0),
        ("Inter", "Mattia Mosconi", 3, "2008-01-01", "ATT", "", "", ""),
        ("Inter", "Piotr Zielinski", 4, "1994-05-20", "CEN", "2024-07-01", "2028-06-30", 8.0),
        ("Lazio", "Ivan Provedel", 5, "1994-03-17", "POR", "2022-07-01", "2027-06-30", 3.0),
        ("Roma", "Untouched Player", 6, "1990-01-01", "DIF", "2020-07-01", "2027-06-30", 1.0),
    ]
    df = pd.DataFrame(
        [
            {
                "club": c, "giocatore": n, "tm_id": str(i), "data_nascita": b, "ruolo": r,
                "arrivo": a, "tipo": "", "scadenza": s, "valore_mln": str(v),
                "valore_data": "2026-06-01" if v != "" else "", "fonte": rose.SNAPSHOT_SOURCE,
                "verificato": "no",
            }
            for c, n, i, b, r, a, s, v in rows
        ]
    )  # fmt: skip
    return df


def _players():
    return pd.DataFrame(
        [
            (1, "Lautaro Martínez", "1997-08-22", "Attack", "Inter Milan", 2025, 85e6),
            (5, "Ivan Provedel", "1994-03-17", "Goalkeeper", "SS Lazio", 2025, 3e6),
            (10, "John Stones", "1994-05-28", "Defender", "Manchester City", 2025, 12e6),
            (11, "Rodrigo Ramos", "2003-11-13", "Defender", "Estoril", 2025, None),
            (12, "Rodrigo Ramos", "2004-02-17", "Defender", "Vizela", 2025, None),
            (13, "Curtis Jones", "2001-01-30", "Midfield", "Liverpool FC", 2025, 35e6),
            (14, "Curtis Jones", "1960-01-01", "Midfield", "Retired FC", 1995, None),
        ],
        columns=[
            "player_id", "name", "date_of_birth", "position", "current_club_name",
            "last_season", "market_value_in_eur",
        ],
    )  # fmt: skip


def _valuations():
    return pd.DataFrame(
        {"player_id": [10, 10, 13], "date": ["2026-06-12", "2025-01-01", "2026-06-08"]}
    ).assign(market_value_in_eur=1.0)


def _list(rows):
    return pd.DataFrame([dict(zip(rose_sync.LIST_COLUMNS, r, strict=True)) for r in rows]).fillna(
        ""
    )


@pytest.fixture
def outcome():
    current = _list(
        [
            ("Inter", "SQUAD", "FW", "Lautaro Martínez", "captain", ""),
            ("Inter", "SQUAD", "MF", "Piotr Zieliński", "", ""),
            ("Inter", "SQUAD", "DF", "John Stones", "", ""),
            ("Inter", "SQUAD", "GK", "Ivan Provedel", "", ""),
            ("Inter", "SQUAD", "MF", "Curtis Jones", "on loan from Liverpool", ""),
            ("Inter", "SQUAD", "DF", "Rodrigo Ramos", "", ""),  # two active namesakes
            ("Inter", "SQUAD2", "FW", "Mattia Mosconi", "", ""),
            ("Inter", "SQUAD2", "DF", "Nobody Known", "", ""),  # youth, not on Transfermarkt
            ("Lazio", "SQUAD", "DF", "Someone New", "", ""),  # first team, not found
        ]
    )
    return rose_sync.reconcile(_squads(), current, _players(), _valuations())


def _row(outcome, name):
    rows = outcome.squads[outcome.squads["giocatore"] == name]
    assert len(rows) == 1, name
    return rows.iloc[0]


def test_confirmed_players_keep_their_data(outcome):
    row = _row(outcome, "Lautaro Martínez")
    assert row["verificato"] == "si"
    assert row["fonte"] == rose.SNAPSHOT_SOURCE
    assert row["tipo"] == "definitivo"
    assert row["scadenza"] == "2029-06-30"
    assert _row(outcome, "Piotr Zielinski")["verificato"] == "si"  # matched without accents


def test_academy_player_without_transfer_is_vivaio(outcome):
    assert _row(outcome, "Mattia Mosconi")["tipo"] == "vivaio"


def test_new_arrival_is_looked_up(outcome):
    row = _row(outcome, "John Stones")
    assert row["tm_id"] == 10
    assert row["data_nascita"] == "1994-05-28"
    assert row["ruolo"] == "DIF"
    assert row["valore_mln"] == 12.0
    assert row["valore_data"] == "2026-06-12"
    assert row["scadenza"] == ""  # old club's contract is not carried over
    assert row["fonte"] == "manuale" and row["verificato"] == "si"


def test_loan_and_namesakes(outcome):
    row = _row(outcome, "Curtis Jones")
    assert row["tm_id"] == 13  # the retired namesake is ignored
    assert row["tipo"] == "prestito"


def test_move_between_clubs_is_reported(outcome):
    provedel = outcome.squads[outcome.squads["giocatore"] == "Ivan Provedel"]
    assert list(provedel["club"]) == ["Inter"]  # removed from Lazio, added to Inter
    note = outcome.report.set_index("nome_fonte").loc["Ivan Provedel", "note"]
    assert "Lazio" in note


def test_departures_are_removed_and_reported(outcome):
    assert "Yann Sommer" not in set(outcome.squads["giocatore"])
    removed = outcome.report[outcome.report["esito"] == "rimosso"]["nome_file"]
    assert set(removed) == {"Yann Sommer", "Ivan Provedel"}


def test_unresolved_and_skipped(outcome):
    assert set(outcome.unresolved["giocatore"]) == {"Rodrigo Ramos"}
    ramos = outcome.unresolved.set_index("giocatore").loc["Rodrigo Ramos", "candidati"]
    assert "11 " in ramos and "12 " in ramos
    skipped = outcome.report[outcome.report["esito"].str.startswith("giovane")]
    assert list(skipped["nome_fonte"]) == ["Nobody Known"]


def test_first_team_player_without_history_is_added_without_id(outcome):
    row = _row(outcome, "Someone New")
    assert row["tm_id"] == "" and row["club"] == "Lazio" and row["ruolo"] == "DIF"
    assert row["verificato"] == "si"


def test_pinned_id_resolves_ambiguity():
    current = _list([("Inter", "SQUAD", "DF", "Rodrigo Ramos", "", "12")])
    out = rose_sync.reconcile(_squads(), current, _players(), _valuations())
    assert out.unresolved.empty
    assert _row(out, "Rodrigo Ramos")["tm_id"] == 12


def test_clubs_not_in_the_list_are_untouched(outcome):
    roma = outcome.squads[outcome.squads["club"] == "Roma"]
    pd.testing.assert_frame_equal(
        roma.reset_index(drop=True).astype(str),
        _squads()[_squads()["club"] == "Roma"].reset_index(drop=True).astype(str),
    )


def test_result_passes_the_file_check(outcome, tmp_path):
    path = tmp_path / "rose.csv"
    outcome.squads.to_csv(path, index=False)
    problems = rose.check(rose.read(path))
    assert rose.is_valid(problems), problems


def test_player_moving_from_an_unprocessed_club_leaves_it():
    current = _list([("Inter", "SQUAD", "GK", "Ivan Provedel", "", "")])
    out = rose_sync.reconcile(_squads(), current, _players(), _valuations(), clubs=["Inter"])
    assert list(out.squads.loc[out.squads["giocatore"] == "Ivan Provedel", "club"]) == ["Inter"]
    assert "rimosso, ora in altra squadra" in set(out.report["esito"])


def test_player_verified_at_two_clubs_is_a_conflict():
    squads = _squads()
    squads.loc[squads["giocatore"] == "Ivan Provedel", "verificato"] = "si"
    current = _list([("Inter", "SQUAD", "GK", "Ivan Provedel", "", "")])
    out = rose_sync.reconcile(squads, current, _players(), _valuations(), clubs=["Inter"])
    assert "conflitto: verificato in due squadre" in set(out.report["esito"])
    assert len(out.squads[out.squads["giocatore"] == "Ivan Provedel"]) == 2
