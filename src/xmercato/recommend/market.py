"""Market suggestions for the current window: needs and candidates for every Serie A club.

Puts together the hand-checked squads (``rose/``), the Transfermarkt tables
(``data/mercato``, from ``xmercato mercato dati``) and the two models of this package.
The output is two small tables that the app reads (folder ``mercato/``).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from xmercato import rose
from xmercato.evaluation import candidates_backtest as cb
from xmercato.ingest import teams as team_names
from xmercato.recommend import availability, performance
from xmercato.recommend import candidates as cand
from xmercato.recommend import needs as nd
from xmercato.recommend.data import MarketData, age, current_squad, latest_position
from xmercato.recommend.slots import LABELS, SLOTS, best_slot

CANDIDATE_COLUMNS = [
    "club",
    "slot",
    "posizione",
    "giocatore",
    "tm_id",
    "eta",
    "club_attuale",
    "campionato_2025_26",
    "valore_mln",
    "minuti_quota",
    "gol",
    "assist",
    "scadenza",
    "ruolo_previsto",
    "probabilita",
    "rango",
    "esperienza_a",
    "estero",
    "rapporti",
]


def train(
    data: MarketData, seasons: Iterable[int], windows: Iterable[str] = ("gennaio", "estate")
) -> cand.PlausibilityModel:
    frame = cb.window_frames(
        data.player_seasons, data.players, data.transfers, seasons, windows, negatives=300
    )
    return fit(frame)


def fit(frame: pd.DataFrame) -> cand.PlausibilityModel:
    """Fit on a frame from ``window_frames``, correcting for the sampled non-signings."""
    kept = (frame["firmato"] == 0).sum()
    pool = frame.groupby(["club", "season", "window"])["negativi_pool"].first().sum()
    return cand.PlausibilityModel().fit(frame, frame["firmato"].to_numpy(), kept / pool)


def _with_slots(data: MarketData) -> pd.DataFrame:
    ps = data.player_seasons
    listed = ps["player_id"].map(data.players.set_index("player_id")["sub_position"])
    return ps.assign(slot=best_slot(ps["posizione"], listed))


def club_ids(data: MarketData, season: str) -> dict[int, str]:
    mapping = rose.match_clubs(data.clubs, rose.SERIE_A[season])
    return dict(zip(mapping["tm_club_id"], mapping["club"], strict=True))


SQUAD_COLUMNS = [
    "club", "giocatore", "ruolo", "slot", "data_nascita", "eta", "valore", "scadenza", "tipo",
    "in_scadenza", "tm_id",
]  # fmt: skip


@dataclass
class NeedParts:
    """Everything the needs are computed from, small enough to ship with the app.

    ``squad``: checked squads with slot, value, age and contract. ``usage``: starters per
    game in each slot. ``teams`` (optional): department form this season. ``forwards``
    (optional): goals+assists of every attacking player, from the scorers.
    """

    squad: pd.DataFrame
    usage: pd.DataFrame
    teams: pd.DataFrame | None = None
    forwards: pd.DataFrame | None = None

    FILES = {
        "squad": "rosa",
        "usage": "utilizzo",
        "teams": "forma_squadre",
        "forwards": "forma_attaccanti",
    }

    def save(self, folder: str | Path, tag: str) -> None:
        for field_name, stem in self.FILES.items():
            table = getattr(self, field_name)
            if table is not None:
                table.to_csv(Path(folder) / f"{stem}_{tag}.csv", index=False)

    @classmethod
    def load(cls, folder: str | Path, tag: str) -> NeedParts:
        tables = {}
        for field_name, stem in cls.FILES.items():
            path = Path(folder) / f"{stem}_{tag}.csv"
            tables[field_name] = pd.read_csv(path) if path.exists() else None
        if tables["squad"] is None or tables["usage"] is None:
            raise FileNotFoundError(f"Mancano rosa e utilizzo per {tag} in {folder}")
        return cls(**tables)


def parts_now(
    squads: pd.DataFrame,
    data: MarketData,
    as_of: pd.Timestamp,
    last_season: int,
    season: str,
    history: pd.DataFrame | None = None,
    scorers: pd.DataFrame | None = None,
) -> NeedParts:
    """The pieces of the needs for the current squads.

    With ``history`` (results, as from ``xmercato storico``) they include how each
    department is doing this season; with ``scorers`` too, the attacking players.
    """
    squad = current_squad(squads, data, as_of, last_season)
    squad = squad.dropna(subset=["slot"]).reset_index(drop=True)
    usage = nd.usage(_with_slots(data), club_ids(data, season), last_season)
    teams = forwards = None
    season_start = int(season[:4])
    if history is not None and (history["season"] == season_start).any():
        teams = performance.team_form(history, season_start)
        if scorers is not None and not scorers.empty:
            names = team_names.map_names(set(scorers["squadra"]), set(squad["club"]))
            scorers = scorers.assign(squadra=scorers["squadra"].map(names))
            rates = performance.fit_rates(_with_slots(data))
            games = teams.set_index("club")["partite"]
            forwards = performance.forward_stats(squad, scorers, rates, games)
    return NeedParts(squad[SQUAD_COLUMNS], usage, teams, forwards)


def needs_from_parts(
    parts: NeedParts,
    window: str,
    opens: pd.Timestamp,
    absences: pd.DataFrame | None = None,
    today: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(needs table, squad with an availability column) from the precomputed pieces.

    Used by ``xmercato mercato suggerisci`` and live by the app, so that a change to the
    injury list shows at once. ``absences`` as from ``availability.read``.
    """
    today = today if today is not None else min(opens, pd.Timestamp.today().normalize())
    squad = parts.squad.copy()
    squad["stato"] = "disponibile"
    available, notes, out, injured = squad, None, set(), set()
    if absences is not None and len(absences):
        available, notes, injured_rows = availability.apply(
            squad, absences, today, window_end(opens, window)
        )
        gone = squad.index.difference(available.index)
        squad.loc[list(injured_rows), "stato"] = "infortunato"
        squad.loc[gone, "stato"] = "fuori per la finestra"
        out = set(zip(squad.loc[gone, "club"], squad.loc[gone, "giocatore"], strict=True))
        hurt = squad.loc[list(injured_rows)]
        injured = set(zip(hurt["club"], hurt["giocatore"], strict=True))
    form = None
    if parts.teams is not None:
        players = None
        if parts.forwards is not None:
            players = performance.player_form(parts.forwards, parts.usage, out, injured)
        form = performance.form_needs(parts.teams, players)
    needs = nd.needs(available, parts.usage, window, form=form, absences=notes)
    return needs, squad


def needs_now(
    squads: pd.DataFrame,
    data: MarketData,
    as_of: pd.Timestamp,
    last_season: int,
    window: str,
    season: str,
    history: pd.DataFrame | None = None,
    scorers: pd.DataFrame | None = None,
    absences: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(needs table, squad with slots) for the current squads, in one go."""
    parts = parts_now(squads, data, as_of, last_season, season, history, scorers)
    return needs_from_parts(parts, window, as_of, absences)


def window_end(opens: pd.Timestamp, window: str) -> pd.Timestamp:
    """When the window closes: a month after it opens in January, 1 September in summer."""
    if window == "gennaio":
        return opens + pd.Timedelta(days=31)
    return pd.Timestamp(year=opens.year, month=9, day=1)


def expected_role(value: pd.Series, starters_value: float) -> pd.Series:
    """Titolare / rotazione / riserva, from value against the slot's current starters."""
    ratio = value / max(starters_value, 0.05)
    return pd.Series(
        np.select([ratio >= 1.0, ratio >= 0.5], ["titolare", "rotazione"], "riserva"),
        index=value.index,
    )


def candidates_now(
    squad: pd.DataFrame,
    needs_table: pd.DataFrame,
    data: MarketData,
    model: cand.PlausibilityModel,
    as_of: pd.Timestamp,
    last_season: int,
    per_slot: int = 40,
    season: str = "2026_27",
    abroad: int = 15,
) -> pd.DataFrame:
    """The ``per_slot`` most plausible candidates of every club in every slot, plus the
    ``abroad`` most plausible among those playing abroad (``estero``: neither in Serie A
    last season nor in a Serie A squad now)."""
    ps = _with_slots(data)
    slots = pd.Series(
        best_slot(
            data.players["player_id"].map(latest_position(ps, last_season)),
            data.players["sub_position"],
        ).to_numpy(),
        index=data.players["player_id"].to_numpy(),
    )
    pool = cand.pool(ps, data.players, last_season, slots)
    info = data.players.set_index("player_id")
    # Where everyone plays now: the checked squads for Serie A, else the July snapshot.
    in_squads = squad.dropna(subset=["tm_id"]).set_index("tm_id")["club"]
    ours = club_ids(data, season)
    # Listed at a Serie A club in July but missing from its checked squad: he has left.
    listed_club = pool["player_id"].map(info["current_club_id"]).map(ours)
    left = "ha lasciato " + listed_club
    pool["club_attuale"] = (
        pool["player_id"]
        .map(in_squads)
        .fillna(left)
        .fillna(pool["player_id"].map(info["current_club_name"]))
    )
    pool["campionato_2025_26"] = (
        pool["competition_id"].map(cand.LEAGUE_GROUPS).fillna(pool["competition_id"])
    )
    pool["estero"] = (pool["competition_id"] != "IT1") & ~pool["club_attuale"].isin(
        set(ours.values())
    )
    pool["scadenza"] = pool["player_id"].map(info["contract_expiration_date"]).astype(str).str[:10]
    deals = cand.relations(data.transfers, as_of)
    ids = {name: tm for tm, name in ours.items()}
    reference = squad.groupby("club")["valore"].apply(
        lambda v: float(np.exp(np.log(v.dropna().clip(lower=0.05).nlargest(11)).median()))
    )
    starters = needs_table.set_index(["club", "slot"])["valore_titolari"]

    out = []
    for club, ref in reference.items():
        others = pool[pool["club_attuale"] != club]
        x = cand.features(others, ids[club], ref, deals, as_of)
        scored = others.assign(punteggio=model.score(x), probabilita=model.probability(x))
        for slot in SLOTS:
            here = scored[scored["slot"] == slot]
            if here.empty:
                continue
            here = here.assign(rango=here["punteggio"].rank(ascending=False, method="first"))
            top = pd.concat(
                [
                    here.nlargest(per_slot, "punteggio"),
                    here[here["estero"]].nlargest(abroad, "punteggio"),
                ]
            )
            top = top[~top.index.duplicated()].sort_values("rango")
            top = top.assign(
                club=club,
                rango=top["rango"].astype(int),
                ruolo_previsto=expected_role(top["valore"], float(starters.get((club, slot), ref))),
                rapporti=top["club_id"].map(
                    lambda c, club_id=ids[club]: int(
                        deals.get((min(c, club_id), max(c, club_id)), 0)
                    )
                ),
            )
            out.append(top)
    result = pd.concat(out, ignore_index=True)
    result = result.rename(columns={"player_id": "tm_id", "valore": "valore_mln"})
    result["posizione"] = result["slot"].map(LABELS)
    result["minuti_quota"] = result["minuti_quota"].round(2)
    result["valore_mln"] = result["valore_mln"].round(2)
    result["esperienza_a"] = result["esperienza_a"].astype(bool)
    result["eta"] = age(result["nascita"], as_of).round(1)
    result["probabilita"] = result["probabilita"].round(4)
    return result[CANDIDATE_COLUMNS]
