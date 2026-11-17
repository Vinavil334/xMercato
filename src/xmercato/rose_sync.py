"""Bring a squad file up to date with a list of current squads.

The list (``rose/fonti/<source>_<season>.csv``) says who is in each squad *now*, by name,
as published by a public source. Reconciling it with the squad file means:

- players already in the file are **confirmed** (``verificato = si``);
- players in the list but not in the file are **added**, looking up their Transfermarkt
  id, birth date, role and value in the Transfermarkt players table;
- players in the file but not in the list have **left** and are removed.

Names are matched after removing accents and punctuation, allowing for a missing middle
name ("Pio Esposito" / "Francesco Pio Esposito") and small spelling differences. When a
name cannot be resolved to exactly one Transfermarkt player the row is not guessed: it is
reported, and the list can pin it with an explicit ``tm_id``. A first-team player that
nobody on Transfermarkt matches (e.g. coming from a league the snapshot does not cover) is
added without ``tm_id``.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

from xmercato import rose

LIST_COLUMNS = ["club", "tabella", "ruolo_fonte", "giocatore", "nota", "tm_id"]
_ROLE_FROM_SOURCE = {"GK": "POR", "DF": "DIF", "MF": "CEN", "FW": "ATT"}
_ROLE_FROM_TM = {"Goalkeeper": "POR", "Defender": "DIF", "Midfield": "CEN", "Attack": "ATT"}
SAME_NAME = 0.86  # similarity above which two names are taken to be the same person
YOUTH_AGE = 23  # with no recorded transfer in, a player this age or younger is from the academy


def normalise(name: str) -> str:
    """'Hakan Çalhanoğlu' -> 'hakan calhanoglu'; 'Loftus-Cheek' -> 'loftus cheek'."""
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("ı", "i").replace("ø", "o").replace("ł", "l").replace("đ", "d")
    text = text.replace("ß", "ss").replace("æ", "ae")
    return re.sub(r"[^a-z]+", " ", text.lower()).strip()


def similarity(a: str, b: str) -> float:
    """1.0 for the same name; high when one name is the other plus extra given names."""
    na, nb = normalise(a), normalise(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = na.split(), nb.split()
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    # Every token of the shorter name appears in the longer one, surname included.
    if len(short) >= 2 and set(short) <= set(long_) and short[-1] in long_:
        return 0.95
    return difflib.SequenceMatcher(None, na, nb).ratio()


@dataclass
class Outcome:
    squads: pd.DataFrame
    report: pd.DataFrame  # one row per decision, for review
    unresolved: pd.DataFrame = field(default_factory=pd.DataFrame)


def _surname_index(players: pd.DataFrame) -> dict[str, list[int]]:
    index: dict[str, list[int]] = {}
    for pos, name in enumerate(players["name"].astype(str)):
        for token in set(normalise(name).split()):
            if len(token) >= 3:
                index.setdefault(token, []).append(pos)
    return index


def _lookup(
    name: str, role: str, players: pd.DataFrame, index: dict[str, list[int]]
) -> tuple[pd.Series | None, list[str]]:
    """The one Transfermarkt player called ``name``, or None with the candidates seen."""
    tokens = [t for t in normalise(name).split() if len(t) >= 3]
    rows = sorted({pos for t in tokens for pos in index.get(t, [])})
    if not rows:
        return None, []
    pool = players.iloc[rows]
    scores = pool["name"].map(lambda n: similarity(name, n))
    pool = pool.assign(_score=scores)[scores >= SAME_NAME]
    if pool.empty:
        return None, []
    describe = [
        f"{r.player_id} {r.name} "
        f"({str(r.date_of_birth)[:4]}, {r.current_club_name}, {r.last_season})"
        for r in pool.itertuples()
    ]
    if len(pool) == 1:
        return pool.iloc[0], describe
    # Several people with the same name: keep the active ones in the right role.
    best = pool[pool["_score"] == pool["_score"].max()]
    active = best[best["last_season"] >= best["last_season"].max() - 1]
    if role:
        same_role = active[active["position"].map(_ROLE_FROM_TM) == role]
        if len(same_role) >= 1:
            active = same_role
    if len(active) == 1:
        return active.iloc[0], describe
    return None, describe


def reconcile(
    squads: pd.DataFrame,
    current: pd.DataFrame,
    players: pd.DataFrame,
    valuations: pd.DataFrame,
    season: str = "2026_27",
    clubs: list[str] | None = None,
) -> Outcome:
    """Apply ``current`` (the list of current squads) to ``squads`` for the given clubs.

    Clubs not in ``clubs`` (default: those present in ``current``) are left untouched.
    Players in a secondary table (``tabella != SQUAD``) who cannot be found on
    Transfermarkt are skipped rather than reported as problems: they are youth players
    with no history yet.
    """
    clubs = clubs or sorted(current["club"].unique())
    season_start = pd.Timestamp(f"{season[:4]}-07-01")
    players = players.reset_index(drop=True)
    index = _surname_index(players)
    by_id = players.set_index("player_id")
    valued_on = valuations.groupby("player_id")["date"].max().str.slice(0, 10)

    kept_rows, report, unresolved = [], [], []
    for club in clubs:
        mine = squads[squads["club"] == club].copy()
        mine["_matched"] = False
        listed = current[current["club"] == club]

        for item in listed.itertuples():
            note = str(item.nota or "")
            on_loan = "on loan" in note.lower() or "prestito" in note.lower()
            role = _ROLE_FROM_SOURCE.get(str(item.ruolo_fonte), "")
            pinned = str(item.tm_id or "").strip()

            # 1. Already in the squad file?
            if pinned:
                hit = mine.index[mine["tm_id"].astype(str) == pinned]
            else:
                scores = mine["giocatore"].map(lambda n, it=item: similarity(it.giocatore, n))
                scores = scores[~mine["_matched"]]
                hit = scores.index[scores >= SAME_NAME] if len(scores) else []
                if len(hit) > 1:
                    hit = [scores.idxmax()]
            if len(hit):
                i = hit[0]
                mine.loc[i, "_matched"] = True
                row = mine.loc[i].copy()
                if on_loan:
                    tipo = "prestito"
                elif row["arrivo"] == "" and _age(row["data_nascita"], season_start) <= YOUTH_AGE:
                    tipo = "vivaio"
                else:
                    tipo = row["tipo"] or "definitivo"
                row["tipo"] = tipo
                row["verificato"] = "si"
                kept_rows.append(row)
                report.append((club, "confermato", item.giocatore, row["giocatore"], ""))
                continue

            # 2. New arrival: find them on Transfermarkt.
            if pinned:
                found = by_id.loc[int(pinned)].copy() if int(pinned) in by_id.index else None
                if found is not None:
                    found["player_id"] = int(pinned)
                seen = [] if found is not None else [f"tm_id {pinned} non trovato"]
            else:
                found, seen = _lookup(item.giocatore, role, players, index)
            if found is None:
                if seen:  # namesakes: do not guess
                    unresolved.append((club, item.giocatore, item.ruolo_fonte, "; ".join(seen)))
                    report.append((club, "da risolvere", item.giocatore, "", "; ".join(seen)))
                elif item.tabella != "SQUAD":
                    report.append((club, "giovane non trovato, escluso", item.giocatore, "", ""))
                else:  # first-team player with no Transfermarkt history in the snapshot
                    kept_rows.append(
                        pd.Series(
                            {
                                **dict.fromkeys(rose.COLUMNS, ""),
                                "club": club,
                                "giocatore": item.giocatore,
                                "ruolo": role,
                                "tipo": "prestito" if on_loan else "",
                                "fonte": "manuale",
                                "verificato": "si",
                            }
                        )
                    )
                    report.append((club, "aggiunto senza tm_id", item.giocatore, "", ""))
                continue
            pid = int(found["player_id"])
            if (squads["tm_id"].astype(str) == str(pid)).any() and not (
                mine["tm_id"].astype(str) == str(pid)
            ).any():
                origin = squads.loc[squads["tm_id"].astype(str) == str(pid), "club"].iloc[0]
                note_move = f"era nella bozza del {origin}"
            else:
                note_move = ""
            value = pd.to_numeric(found.get("market_value_in_eur"), errors="coerce")
            kept_rows.append(
                pd.Series(
                    {
                        "club": club,
                        "giocatore": str(found["name"]),
                        "tm_id": pid,
                        "data_nascita": str(found["date_of_birth"])[:10],
                        "ruolo": _ROLE_FROM_TM.get(found.get("position"), role),
                        "arrivo": "",
                        "tipo": "prestito" if on_loan else "definitivo",
                        "scadenza": "",  # the contract in the snapshot is with the old club
                        "valore_mln": round(value / 1e6, 2) if pd.notna(value) else "",
                        "valore_data": valued_on.get(pid, "") if pd.notna(value) else "",
                        "fonte": "manuale",
                        "verificato": "si",
                    }
                )
            )
            report.append((club, "aggiunto", item.giocatore, str(found["name"]), note_move))

        for row in mine[~mine["_matched"]].itertuples():
            report.append((club, "rimosso", "", row.giocatore, ""))

    updated = pd.DataFrame(kept_rows, columns=rose.COLUMNS) if kept_rows else squads.iloc[0:0]
    untouched = squads[~squads["club"].isin(clubs)]
    # A player confirmed at a new club leaves his old one, unless the old row was verified.
    placed = set(updated["tm_id"].astype(str)) - {""}
    elsewhere = untouched["tm_id"].astype(str).isin(placed)
    moved = elsewhere & (untouched["verificato"] != "si")
    for row in untouched[moved].itertuples():
        report.append((row.club, "rimosso, ora in altra squadra", "", row.giocatore, ""))
    for row in untouched[elsewhere & ~moved].itertuples():
        report.append((row.club, "conflitto: verificato in due squadre", "", row.giocatore, ""))
    untouched = untouched[~moved]
    out = pd.concat([untouched, updated[rose.COLUMNS]], ignore_index=True)
    order = {r: k for k, r in enumerate(rose.RUOLI)}
    out = out.assign(
        _club=out["club"].map({c: k for k, c in enumerate(rose.SERIE_A[season])}),
        _ruolo=out["ruolo"].map(order),
        _valore=pd.to_numeric(out["valore_mln"], errors="coerce"),
    ).sort_values(["_club", "_ruolo", "_valore"], ascending=[True, True, False], na_position="last")
    out = out[rose.COLUMNS].reset_index(drop=True)
    return Outcome(
        squads=out,
        report=pd.DataFrame(report, columns=["club", "esito", "nome_fonte", "nome_file", "note"]),
        unresolved=pd.DataFrame(unresolved, columns=["club", "giocatore", "ruolo", "candidati"]),
    )


def _age(birth: str, on: pd.Timestamp) -> float:
    born = pd.to_datetime(str(birth)[:10], format="%Y-%m-%d", errors="coerce")
    return (on - born).days / 365.25 if pd.notna(born) else float("inf")


def read_list(path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False, comment="#")
    missing = [c for c in LIST_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"La lista {path} non ha le colonne {missing}")
    return df.apply(lambda s: s.str.strip())
