import pandas as pd
import pytest

from xmercato import cli, rose

CLUBS = rose.SERIE_A["2026_27"]


def _tm_snapshot():
    """A tiny dataset in the Transfermarkt layout, with the traps the real one has."""
    clubs = pd.DataFrame(
        [
            (46, "Football Club Internazionale Milano S.p.A.", "IT1", 2025),
            (5, "Associazione Calcio Milan", "IT1", 2025),
            (12, "Associazione Sportiva Roma", "IT1", 2025),
            (999, "Roma City FC", "XX1", 2020),  # matches "Roma" too, but not Serie A
            (607, "Venezia FC", "IT1", 2024),  # promoted: last Serie A season is older
            (276, "Hellas Verona FC", "IT1", 2025),  # relegated: not in 2026/27
        ],
        columns=["club_id", "name", "domestic_competition_id", "last_season"],
    )
    # Every other 2026/27 club, so that the matching finds all twenty.
    others = [c for c in CLUBS if c not in ("Inter", "Milan", "Roma", "Venezia")]
    clubs = pd.concat(
        [
            clubs,
            pd.DataFrame(
                {
                    "club_id": range(2000, 2000 + len(others)),
                    "name": [f"{c} Calcio" for c in others],
                    "domestic_competition_id": "IT1",
                    "last_season": 2025,
                }
            ),
        ],
        ignore_index=True,
    )
    players = pd.DataFrame(
        [
            (1, "Portiere Uno", "1995-01-02 00:00:00", "Goalkeeper", 46, 2025, "2028-06-30", 5e6),
            (2, "Punta Due", "2000-05-06", "Attack", 46, 2025, "2030-06-30 00:00:00", 80e6),
            (3, "Mediano Tre", "1999-03-04 00:00:00", "Midfield", 5, 2025, None, None),
            (4, "Ritirato Quattro", "1985-01-01 00:00:00", "Defender", 12, 2021, None, 1e6),
            (5, "Retrocesso Cinque", "1998-01-01 00:00:00", "Defender", 276, 2025, None, 2e6),
            (6, "Esterno Sei", "2003-07-08 00:00:00", "Defender", 607, 2025, None, 3.25e6),
        ],
        columns=[
            "player_id", "name", "date_of_birth", "position", "current_club_id",
            "last_season", "contract_expiration_date", "market_value_in_eur",
        ],
    )  # fmt: skip
    transfers = pd.DataFrame(
        [
            (2, "2019-07-01", 999),
            (2, "2023-08-10", 46),
            (2, "2021-01-15", 46),  # older move to the same club: the latest wins
            (6, "2025-07-20", 607),
        ],
        columns=["player_id", "transfer_date", "to_club_id"],
    )
    valuations = pd.DataFrame(
        [
            (1, "2026-06-12"),
            (1, "2025-12-01"),
            (2, "2026-06-12"),
            (6, "2026-05-30"),
            (4, "2021-01-01"),
        ],
        columns=["player_id", "date"],
    ).assign(market_value_in_eur=1.0)
    return {
        "clubs": clubs,
        "players": players,
        "transfers": transfers,
        "player_valuations": valuations,
    }


@pytest.fixture
def squads():
    out, _ = rose.draft(_tm_snapshot())
    return out


def test_club_matching_prefers_serie_a_and_respects_word_boundaries():
    mapping = rose.match_clubs(_tm_snapshot()["clubs"], CLUBS).set_index("club")
    assert len(mapping) == 20
    assert mapping.loc["Inter", "tm_club_id"] == 46
    assert mapping.loc["Milan", "tm_club_id"] == 5  # not Inter's "Milano"
    assert mapping.loc["Roma", "tm_club_id"] == 12  # not "Roma City FC"
    assert mapping.loc["Venezia", "tm_club_id"] == 607


@pytest.mark.parametrize(
    ("inter_name", "milan_name"),
    [
        ("Football Club Internazionale Milano S.p.A.", "Associazione Calcio Milan"),
        ("Inter Milan", "AC Milan"),
    ],
)
def test_inter_and_milan_are_told_apart(inter_name, milan_name):
    clubs = _tm_snapshot()["clubs"].copy()
    clubs.loc[clubs["club_id"] == 46, "name"] = inter_name
    clubs.loc[clubs["club_id"] == 5, "name"] = milan_name
    mapping = rose.match_clubs(clubs, CLUBS).set_index("club")
    assert mapping.loc["Inter", "tm_club_id"] == 46
    assert mapping.loc["Milan", "tm_club_id"] == 5


def test_two_clubs_on_one_transfermarkt_club_is_an_error():
    clubs = _tm_snapshot()["clubs"].copy()
    clubs.loc[clubs["club_id"] == 5, "name"] = "Roma Milan Club"  # would match both
    clubs = clubs[clubs["club_id"] != 12]
    with pytest.raises(ValueError, match="same Transfermarkt club"):
        rose.match_clubs(clubs, CLUBS)


def test_club_matching_fails_loudly():
    clubs = _tm_snapshot()["clubs"]
    with pytest.raises(ValueError, match="Venezia"):
        rose.match_clubs(clubs[clubs["club_id"] != 607], CLUBS)


def test_draft_rows(squads):
    assert list(squads.columns) == rose.COLUMNS
    # Retired (last season 2021) and relegated-club players are left out.
    assert sorted(squads["tm_id"]) == [1, 2, 3, 6]
    row = squads.set_index("tm_id").loc[2]
    assert row["club"] == "Inter"
    assert row["ruolo"] == "ATT"
    assert row["data_nascita"] == "2000-05-06"
    assert row["arrivo"] == "2023-08-10"
    assert row["scadenza"] == "2030-06-30"
    assert row["valore_mln"] == 80.0
    assert row["valore_data"] == "2026-06-12"
    assert row["tipo"] == ""
    assert (squads["fonte"] == rose.SNAPSHOT_SOURCE).all()
    assert (squads["verificato"] == "no").all()
    # Inter first, goalkeeper before forward.
    assert list(squads["tm_id"][:2]) == [1, 2]


def test_draft_missing_values_stay_empty(squads):
    row = squads.set_index("tm_id").loc[3]
    assert row["arrivo"] == "" and row["scadenza"] == "" and row["valore_data"] == ""
    assert pd.isna(row["valore_mln"])


def test_draft_round_trips_through_the_check(tmp_path, squads):
    path = tmp_path / "rose.csv"
    squads.to_csv(path, index=False)
    problems = rose.check(rose.read(path))
    assert rose.is_valid(problems), problems
    text = "\n".join(map(str, problems))
    assert "4 righe su 4 ancora da verificare" in text
    assert "Atalanta: nessun giocatore" in text


def _valid_row(**changes):
    row = {
        "club": "Roma", "giocatore": "Mario Rossi", "tm_id": "123456",
        "data_nascita": "2001-03-15", "ruolo": "ATT", "arrivo": "2026-08-20",
        "tipo": "definitivo", "scadenza": "2030-06-30", "valore_mln": "12.5",
        "valore_data": "2026-09-01", "fonte": "manuale", "verificato": "si",
    }  # fmt: skip
    row.update(changes)
    return row


def _errors(rows):
    return [str(p) for p in rose.check(pd.DataFrame(rows)) if p.level == "errore"]


def test_check_accepts_a_good_row():
    assert _errors([_valid_row()]) == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"club": "Pisa"}, "Club non in Serie A"),
        ({"giocatore": " "}, "Nome del giocatore"),
        ({"tm_id": "abc"}, "tm_id mancante"),
        ({"tm_id": ""}, "tm_id mancante"),
        ({"ruolo": "Attaccante"}, "ruolo deve essere"),
        ({"tipo": "comproprietà"}, "tipo deve essere"),
        ({"arrivo": "20/08/2026"}, "arrivo: data non valida"),
        ({"scadenza": "2030-02-30"}, "scadenza: data non valida"),
        ({"valore_mln": "12,5"}, "valore_mln deve essere"),
        ({"valore_mln": "-1"}, "valore_mln deve essere"),
        ({"verificato": "sì"}, "verificato deve essere"),
    ],
)
def test_check_errors(change, message):
    errors = _errors([_valid_row(**change)])
    assert len(errors) == 1 and message in errors[0], errors


def test_check_duplicates_and_line_numbers():
    rows = [_valid_row(), _valid_row(tm_id="7"), _valid_row()]
    (error,) = _errors(rows)
    assert "righe 2, 4" in error  # header is line 1


def test_check_missing_columns():
    problems = rose.check(pd.DataFrame([_valid_row()]).drop(columns=["fonte"]))
    assert [p.level for p in problems] == ["errore"]
    assert "fonte" in problems[0].message


def test_summary_lists_every_club(squads):
    table = rose.summary(squads)
    assert list(table.index) == list(CLUBS)
    assert table.loc["Inter", "giocatori"] == 2
    assert table.loc["Inter", "valore_mln"] == 85.0
    assert table.loc["Atalanta", "giocatori"] == 0


def test_cli_bozza_and_controlla(tmp_path, monkeypatch, capsys):
    for name, table in _tm_snapshot().items():
        table.to_csv(tmp_path / f"{name}.csv.gz", index=False)
    out = tmp_path / "rose" / "serie_a_2026_27.csv"
    cli.main(["rose", "bozza", "--tm", str(tmp_path), "--out", str(out)])
    assert out.exists()
    assert "4 giocatori" in capsys.readouterr().out

    cli.main(["rose", "controlla", str(out)])
    assert "File utilizzabile" in capsys.readouterr().out

    broken = rose.read(out)
    broken.loc[0, "ruolo"] = "?"
    broken.to_csv(out, index=False)
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["rose", "controlla", str(out)])
    assert exit_info.value.code == 1
    assert "ruolo deve essere" in capsys.readouterr().out


def test_tm_url():
    assert rose.tm_url(123).endswith("/spieler/123")
    with pytest.raises(ValueError):
        rose.tm_url("1; rm")


def test_expired_contracts_are_flagged_until_verified():
    rows = [_valid_row(tm_id="1", scadenza="2026-06-30", verificato="no"), _valid_row(tm_id="2")]
    text = "\n".join(str(p) for p in rose.check(pd.DataFrame(rows)))
    assert "1 giocatori con contratto scaduto prima del 01/07/2026" in text
    assert "righe 2)" in text
    rows[0]["verificato"] = "si"  # checked by hand: e.g. renewed and file not yet updated
    text = "\n".join(str(p) for p in rose.check(pd.DataFrame(rows)))
    assert "contratto scaduto" not in text
