"""Injured and unavailable players, from a hand-kept list (``rose/indisponibili_*.csv``).

No free source of injuries can be used automatically (see docs/DATI.md), so the list is
kept by hand from public news, with the source of every row. It does two things:

- a player out until after the window closes does not count in the squad: the slot is
  missing a player, and his replacement becomes the likely starter;
- an injured player is left out of the attacking-form check, so that a forward who has
  not scored because he has not played is not taken for one who is playing badly.

``rientro_stimato`` is our reading of the expected return ("dicembre" -> 15 December,
"nel 2027" -> 15 February, a cruciate ligament "nel 2027" -> 31 March); empty when the
news gives no date. Rows whose date has passed are ignored.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from xmercato.rose_sync import similarity

COLUMNS = ["club", "giocatore", "problema", "rientro", "rientro_stimato", "fonte", "aggiornato"]


def read(path: str | Path) -> pd.DataFrame:
    table = pd.read_csv(path, dtype=str).fillna("")
    missing = [c for c in COLUMNS if c not in table.columns]
    if missing:
        raise ValueError(f"{path}: mancano le colonne {missing}")
    table["rientro_stimato"] = pd.to_datetime(table["rientro_stimato"], errors="coerce")
    table["aggiornato"] = pd.to_datetime(table["aggiornato"], errors="coerce")
    return table


def match(squad: pd.DataFrame, absences: pd.DataFrame, threshold: float = 0.85) -> pd.Series:
    """For each row of ``absences``, the index of the player in ``squad`` (NaN if not found)."""
    out = pd.Series(float("nan"), index=absences.index)
    for i, row in absences.iterrows():
        club = squad[squad["club"] == row["club"]]
        if club.empty:
            continue
        scores = club["giocatore"].map(lambda name, row=row: similarity(row["giocatore"], name))
        if scores.max() >= threshold:
            out[i] = scores.idxmax()
    return out


def apply(
    squad: pd.DataFrame, absences: pd.DataFrame, as_of: pd.Timestamp, until: pd.Timestamp
) -> tuple[pd.DataFrame, pd.DataFrame, set]:
    """Split the squad by availability.

    Returns the squad without the players out beyond ``until``, a note per club and slot
    naming them, and the squad indices of everyone still injured on ``as_of`` (for the
    form check). Rows that do not match a squad player raise an error, so that a typo
    does not silently drop an absence.
    """
    index = match(squad, absences)
    unknown = absences[index.isna()]
    if len(unknown):
        names = ", ".join(f"{r.giocatore} ({r.club})" for r in unknown.itertuples())
        raise ValueError(f"Indisponibili non trovati nelle rose: {names}")
    current = absences.assign(row=index.astype(int))
    current = current[current["rientro_stimato"].isna() | (current["rientro_stimato"] > as_of)]
    long_out = current[current["rientro_stimato"] > until]

    notes = []
    for row in long_out.itertuples():
        player = squad.loc[row.row]
        note = f"{player['giocatore']} ({row.problema}, rientro {row.rientro})"
        notes.append({"club": player["club"], "slot": player["slot"], "nota_assenze": note})
    notes = pd.DataFrame(notes, columns=["club", "slot", "nota_assenze"])
    notes = notes.groupby(["club", "slot"], as_index=False)["nota_assenze"].agg("; ".join)
    return squad.drop(index=long_out["row"]), notes, set(current["row"])


def to_csv(absences: pd.DataFrame) -> str:
    """The list in the file format (dates back to text), sorted by club and player."""
    out = absences[COLUMNS].copy()
    for column in ("rientro_stimato", "aggiornato"):
        out[column] = pd.to_datetime(out[column], errors="coerce").dt.strftime("%Y-%m-%d")
    return out.fillna("").sort_values(["club", "giocatore"]).to_csv(index=False)


def candidate_status(
    candidates: pd.DataFrame,
    absences: pd.DataFrame,
    today: pd.Timestamp,
    until: pd.Timestamp,
    threshold: float = 0.85,
) -> tuple[pd.Series, pd.Series]:
    """(note, out for the window) for each candidate playing at a club on the list.

    ``candidates`` needs ``giocatore`` and ``club_attuale``. Only Serie A clubs are on the
    list, so players abroad are never flagged.
    """
    note = pd.Series("", index=candidates.index)
    out = pd.Series(False, index=candidates.index)
    current = absences[absences["rientro_stimato"].isna() | (absences["rientro_stimato"] > today)]
    for row in current.itertuples():
        here = candidates[candidates["club_attuale"] == row.club]
        if here.empty:
            continue
        same = here["giocatore"].map(lambda name, row=row: similarity(row.giocatore, name))
        hit = same[same >= threshold].index
        note[hit] = f"infortunato ({row.problema}, rientro {row.rientro})"
        out[hit] = bool(pd.notna(row.rientro_stimato) and row.rientro_stimato > until)
    return note, out
