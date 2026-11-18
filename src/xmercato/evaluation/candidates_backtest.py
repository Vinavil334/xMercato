"""Backtest of the candidate lists: were the players clubs really signed near the top?

For every past window and Serie A club the whole pool of covered players is scored, using
only what was known before the window (stats of the previous season, values on 1 July).
The model is trained on the windows before the test ones; for each real signing that came
from the pool we record its rank among the candidates of the same slot.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from xmercato.evaluation import needs_backtest as nb
from xmercato.recommend import candidates as cand
from xmercato.recommend.slots import best_slot


def reference_values(squad: pd.DataFrame) -> pd.Series:
    """Value of a typical starter of each club (median of its eleven most valuable)."""
    return (
        squad.dropna(subset=["valore"])
        .groupby("club")["valore"]
        .apply(lambda v: float(np.exp(np.log(v.clip(lower=0.05).nlargest(11)).median())))
    )


def window_frames(
    player_seasons: pd.DataFrame,
    players: pd.DataFrame,
    transfers: pd.DataFrame,
    seasons: Iterable[int],
    windows: Iterable[str] = ("gennaio", "estate"),
    negatives: int | None = 300,
    seed: int = 0,
) -> pd.DataFrame:
    """Candidate rows for every club and window, with ``firmato`` = 1 for real signings.

    With ``negatives`` set, only that many random non-signings are kept per club and window
    (for training); with ``None`` the whole pool is kept (for testing).
    """
    rng = np.random.default_rng(seed)
    ps = player_seasons.assign(
        slot=best_slot(
            player_seasons["posizione"],
            player_seasons["player_id"].map(players.set_index("player_id")["sub_position"]),
        )
    )
    frames = []
    for window in windows:
        for season in seasons:
            start, _ = nb.window_dates(season, window)
            clubs = nb.clubs_of_season(ps, season)
            squads = nb.squad_before(ps, players, season, window)
            reference = reference_values(squads[squads["club"].isin(clubs)])
            slots = nb.with_slots(ps, players, season - 1)
            candidates = cand.pool(ps, players, season - 1, slots)
            deals = cand.relations(transfers, start)
            signed = nb.arrivals(transfers, reference.index, season, window)
            signed = set(zip(signed["to_club_id"], signed["player_id"], strict=True))
            for club, ref in reference.items():
                c = candidates[candidates["club_id"] != club]
                y = np.array([(club, p) in signed for p in c["player_id"]], dtype=float)
                pool_negatives = int((y == 0).sum())
                if negatives is not None:
                    keep = y.astype(bool)
                    neg = np.flatnonzero(~keep)
                    keep[rng.choice(neg, size=min(negatives, len(neg)), replace=False)] = True
                    c, y = c[keep], y[keep]
                x = cand.features(c, club, ref, deals, start)
                frames.append(
                    pd.concat([c.drop(columns=[k for k in x if k in c]), x], axis=1).assign(
                        firmato=y,
                        club=club,
                        season=season,
                        window=window,
                        negativi_pool=pool_negatives,
                    )
                )
    return pd.concat(frames, ignore_index=True)


def ranks(frame: pd.DataFrame, score: np.ndarray) -> pd.DataFrame:
    """Rank of each real signing among the candidates of the same club, window and slot."""
    f = frame.assign(punteggio=score)
    f["rango"] = f.groupby(["club", "season", "window", "slot"])["punteggio"].rank(
        ascending=False, method="average"
    )
    f["su"] = f.groupby(["club", "season", "window", "slot"])["punteggio"].transform("size")
    return f[f["firmato"] == 1][
        ["season", "window", "club", "player_id", "giocatore", "slot", "rango", "su"]
    ]


def summary(r: pd.DataFrame) -> dict[str, float]:
    return {
        "acquisti": len(r),
        "rango_mediano": float(r["rango"].median()),
        "percentile_mediano": float((r["rango"] / r["su"]).median()),
        "primi_10": float((r["rango"] <= 10).mean()),
        "primi_50": float((r["rango"] <= 50).mean()),
        "primi_100": float((r["rango"] <= 100).mean()),
    }
