"""Hand-maintained squad lists (``rose/serie_a_<season>.csv``).

The file format is described in docs/DATI.md. This module:

- builds a *draft* from the last Transfermarkt snapshot (July 2026), so that by hand one
  only has to apply the summer transfers;
- checks a squad file and reports problems in two levels: errors (the file cannot be
  used) and warnings (the file is usable but incomplete).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

COLUMNS = [
    "club",
    "giocatore",
    "tm_id",
    "data_nascita",
    "ruolo",
    "arrivo",
    "tipo",
    "scadenza",
    "valore_mln",
    "valore_data",
    "fonte",
    "verificato",
]
RUOLI = ("POR", "DIF", "CEN", "ATT")
TIPI = ("definitivo", "prestito", "prestito_diritto", "prestito_obbligo", "vivaio")
DATE_COLUMNS = ("data_nascita", "arrivo", "scadenza", "valore_data")

# Club names as in the football-data.co.uk results files, so squads join the match data.
SERIE_A = {
    "2026_27": (
        "Atalanta", "Bologna", "Cagliari", "Como", "Fiorentina", "Frosinone", "Genoa",
        "Inter", "Juventus", "Lazio", "Lecce", "Milan", "Monza", "Napoli", "Parma", "Roma",
        "Sassuolo", "Torino", "Udinese", "Venezia",
    ),
}  # fmt: skip

# How each club shows up in Transfermarkt's official club names.
_TM_NAME_PATTERNS = {
    "Atalanta": r"\bAtalanta\b",
    "Bologna": r"\bBologna\b",
    "Cagliari": r"\bCagliari\b",
    "Como": r"\bComo\b",
    "Fiorentina": r"\bFiorentina\b",
    "Frosinone": r"\bFrosinone\b",
    "Genoa": r"\bGenoa\b",
    "Inter": r"\bInter(?:nazionale)?\b",
    "Juventus": r"\bJuventus\b",
    "Lazio": r"\bLazio\b",
    "Lecce": r"\bLecce\b",
    # Not Inter, whose name can be "Inter Milan" or "... Internazionale Milano".
    "Milan": r"^(?!.*\bInter).*\bMilan\b",
    "Monza": r"\bMonza\b",
    "Napoli": r"\bNapoli\b",
    "Parma": r"\bParma\b",
    "Roma": r"\bRoma\b",
    "Sassuolo": r"\bSassuolo\b",
    "Torino": r"\bTorino\b",
    "Udinese": r"\bUdinese\b",
    "Venezia": r"\bVenezia\b",
}

_POSITION_TO_RUOLO = {
    "Goalkeeper": "POR",
    "Defender": "DIF",
    "Midfield": "CEN",
    "Attack": "ATT",
}

SNAPSHOT_SOURCE = "tm_2026_07"  # value of `fonte` for rows coming from the snapshot


# ---------------------------------------------------------------------------- draft


def match_clubs(clubs: pd.DataFrame, names: tuple[str, ...]) -> pd.DataFrame:
    """Find the Transfermarkt ``club_id`` of each club in ``names``.

    Among clubs whose name matches, those that played in Serie A (``IT1``) are preferred,
    then the most recent ``last_season``. Raises if a club has no match at all.
    """
    rows, missing = [], []
    for club in names:
        hits = clubs[clubs["name"].astype(str).str.contains(_TM_NAME_PATTERNS[club], regex=True)]
        if hits.empty:
            missing.append(club)
            continue
        hits = hits.assign(_it1=hits["domestic_competition_id"].eq("IT1")).sort_values(
            ["_it1", "last_season"], ascending=False
        )
        best = hits.iloc[0]
        rows.append(
            {
                "club": club,
                "tm_club_id": int(best["club_id"]),
                "tm_name": best["name"],
                "candidates": len(hits),
            }
        )
    if missing:
        raise ValueError(f"No Transfermarkt club found for: {missing}")
    out = pd.DataFrame(rows)
    shared = out[out["tm_club_id"].duplicated(keep=False)]
    if not shared.empty:
        raise ValueError(f"Several clubs matched the same Transfermarkt club:\n{shared}")
    return out


def _to_date(values: pd.Series) -> pd.Series:
    """Parse the date part of ISO strings, tolerating a time suffix on some rows only."""
    day = values.astype("string").str.slice(0, 10)
    return pd.to_datetime(day, format="%Y-%m-%d", errors="coerce")


def _day(values: pd.Series) -> pd.Series:
    """'2029-06-30 00:00:00' -> '2029-06-30'; missing or unparseable stays empty."""
    return _to_date(values).dt.strftime("%Y-%m-%d").fillna("")


def draft(
    tm: dict[str, pd.DataFrame],
    season: str = "2026_27",
    min_last_season: int = 2025,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Squad draft from a Transfermarkt snapshot.

    Takes every player whose current club is one of the season's clubs and who played in
    a covered league in ``min_last_season`` or later. Returns ``(squads, club_mapping)``.
    Loan status is not in the dataset, so ``tipo`` is left empty and every row is marked
    ``verificato = no``.
    """
    mapping = match_clubs(tm["clubs"], SERIE_A[season])
    club_of = dict(zip(mapping["tm_club_id"], mapping["club"], strict=True))

    players = tm["players"]
    players = players[
        players["current_club_id"].isin(club_of) & (players["last_season"] >= min_last_season)
    ].copy()

    # Arrival: the latest transfer into the player's current club.
    transfers = tm["transfers"]
    arrivals = (
        transfers.merge(players[["player_id", "current_club_id"]], on="player_id")
        .query("to_club_id == current_club_id")
        .assign(transfer_date=lambda d: _to_date(d["transfer_date"]))
        .groupby("player_id")["transfer_date"]
        .max()
    )
    valued_on = (
        tm["player_valuations"]
        .assign(date=lambda d: _to_date(d["date"]))
        .groupby("player_id")["date"]
        .max()
    )

    value = pd.to_numeric(players["market_value_in_eur"], errors="coerce") / 1e6
    out = pd.DataFrame(
        {
            "club": players["current_club_id"].map(club_of),
            "giocatore": players["name"].astype(str).str.strip(),
            "tm_id": players["player_id"].astype(int),
            "data_nascita": _day(players["date_of_birth"]),
            "ruolo": players["position"].map(_POSITION_TO_RUOLO).fillna(""),
            "arrivo": _day(players["player_id"].map(arrivals)),
            "tipo": "",
            "scadenza": _day(players["contract_expiration_date"]),
            "valore_mln": value.round(2),
            "valore_data": _day(players["player_id"].map(valued_on)),
            "fonte": SNAPSHOT_SOURCE,
            "verificato": "no",
        }
    )
    # No value, no valuation date.
    out.loc[out["valore_mln"].isna(), "valore_data"] = ""
    order = {r: k for k, r in enumerate(RUOLI)}
    out = out.sort_values(
        ["club", "ruolo", "valore_mln"],
        key=lambda s: s.map(order).fillna(len(RUOLI)) if s.name == "ruolo" else s,
        ascending=[True, True, False],
        na_position="last",
    )
    return out[COLUMNS].reset_index(drop=True), mapping


# ---------------------------------------------------------------------------- check


@dataclass(frozen=True)
class Problem:
    level: str  # "errore" or "avviso"
    message: str

    def __str__(self) -> str:
        return f"[{self.level}] {self.message}"


def read(path) -> pd.DataFrame:
    """Read a squad file keeping every cell as text, so the check sees what was typed."""
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")


def _rows(mask: pd.Series, limit: int = 5) -> str:
    """File line numbers (header is line 1) of the first rows where ``mask`` holds."""
    lines = [str(i + 2) for i in mask[mask].index[:limit]]
    more = mask.sum() - len(lines)
    return ", ".join(lines) + (f" e altre {more}" if more > 0 else "")


def check(
    squads: pd.DataFrame, season: str = "2026_27", min_size: int = 20, max_size: int = 35
) -> list[Problem]:
    """All problems found in a squad file, errors first."""
    errors: list[str] = []
    warnings: list[str] = []

    missing = [c for c in COLUMNS if c not in squads.columns]
    if missing:
        return [Problem("errore", f"Colonne mancanti: {missing}")]
    df = squads[COLUMNS].astype(str).apply(lambda s: s.str.strip())

    clubs = SERIE_A[season]
    bad = ~df["club"].isin(clubs)
    if bad.any():
        names = sorted(df.loc[bad, "club"].unique())
        errors.append(
            f"Club non in Serie A {season.replace('_', '/')}: {names} (righe {_rows(bad)})"
        )

    if (df["giocatore"] == "").any():
        errors.append(f"Nome del giocatore mancante (righe {_rows(df['giocatore'] == '')})")

    bad = ~df["tm_id"].str.fullmatch(r"[1-9]\d*")
    if bad.any():
        errors.append(f"tm_id mancante o non numerico (righe {_rows(bad)})")
    dup = df["tm_id"].duplicated(keep=False) & ~bad
    if dup.any():
        errors.append(f"Stesso tm_id su più righe (righe {_rows(dup)})")

    bad = ~df["ruolo"].isin(RUOLI)
    if bad.any():
        errors.append(f"ruolo deve essere uno di {list(RUOLI)} (righe {_rows(bad)})")

    bad = ~df["tipo"].isin(("", *TIPI))
    if bad.any():
        errors.append(f"tipo deve essere vuoto o uno di {list(TIPI)} (righe {_rows(bad)})")

    for col in DATE_COLUMNS:
        filled = df[col] != ""
        well_formed = df[col].str.fullmatch(r"\d{4}-\d{2}-\d{2}")
        parsed = pd.to_datetime(df[col].where(filled & well_formed), errors="coerce")
        bad = filled & (~well_formed | parsed.isna())
        if bad.any():
            errors.append(f"{col}: data non valida, usa AAAA-MM-GG (righe {_rows(bad)})")

    filled = df["valore_mln"] != ""
    value = pd.to_numeric(df["valore_mln"].where(filled), errors="coerce")
    bad = filled & (value.isna() | (value < 0))
    if bad.any():
        errors.append(f"valore_mln deve essere un numero in milioni, es. 12.5 (righe {_rows(bad)})")
    bad = filled & (df["valore_data"] == "")
    if bad.any():
        warnings.append(f"valore_mln senza valore_data (righe {_rows(bad)})")

    bad = ~df["verificato"].isin(("si", "no"))
    if bad.any():
        errors.append(f"verificato deve essere 'si' o 'no' (righe {_rows(bad)})")

    # Completeness.
    sizes = df["club"].value_counts()
    for club in clubs:
        n = int(sizes.get(club, 0))
        if n == 0:
            warnings.append(f"{club}: nessun giocatore")
        elif not min_size <= n <= max_size:
            warnings.append(f"{club}: {n} giocatori, fuori dall'intervallo {min_size}-{max_size}")
    season_start = pd.Timestamp(f"{season[:4]}-07-01")
    contract_end = pd.to_datetime(df["scadenza"].where(df["scadenza"] != ""), errors="coerce")
    expired = (contract_end < season_start) & (df["verificato"] == "no")
    if expired.any():
        warnings.append(
            f"{int(expired.sum())} giocatori con contratto scaduto prima del "
            f"{season_start:%d/%m/%Y}: probabilmente svincolati (righe {_rows(expired)})"
        )
    todo = df["verificato"] == "no"
    if todo.any():
        warnings.append(f"{int(todo.sum())} righe su {len(df)} ancora da verificare")
    no_type = (df["tipo"] == "") & (df["verificato"] == "si")
    if no_type.any():
        warnings.append(f"Righe verificate senza tipo (righe {_rows(no_type)})")

    return [Problem("errore", m) for m in errors] + [Problem("avviso", m) for m in warnings]


def summary(squads: pd.DataFrame, season: str = "2026_27") -> pd.DataFrame:
    """Per club: players, of which verified, and squad value in millions."""
    df = squads.copy()
    df["valore"] = pd.to_numeric(df["valore_mln"], errors="coerce")
    df["ok"] = df["verificato"].astype(str).str.strip().eq("si")
    out = df.groupby("club").agg(
        giocatori=("tm_id", "size"), verificati=("ok", "sum"), valore_mln=("valore", "sum")
    )
    out = out.reindex(SERIE_A[season], fill_value=0)
    out["valore_mln"] = out["valore_mln"].round(1)
    return out.rename_axis("club")


def is_valid(problems: list[Problem]) -> bool:
    return not any(p.level == "errore" for p in problems)


def tm_url(tm_id: int | str) -> str:
    """Transfermarkt page of a player, handy for checking a row by hand."""
    if not re.fullmatch(r"\d+", str(tm_id)):
        raise ValueError(f"Not a Transfermarkt id: {tm_id!r}")
    return f"https://www.transfermarkt.it/-/profil/spieler/{tm_id}"
