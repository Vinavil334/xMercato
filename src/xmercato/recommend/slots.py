"""Positions grouped into eight slots, the unit in which squad needs are measured."""

from __future__ import annotations

import pandas as pd

SLOTS = ("POR", "DC", "TD", "TS", "CC", "TRQ", "ALI", "ATT")

LABELS = {
    "POR": "Portiere",
    "DC": "Difensore centrale",
    "TD": "Terzino o esterno destro",
    "TS": "Terzino o esterno sinistro",
    "CC": "Centrocampista centrale",
    "TRQ": "Trequartista o seconda punta",
    "ALI": "Esterno d'attacco",
    "ATT": "Centravanti",
}

# Transfermarkt positions (detailed ones first, then the generic ones some rows have).
_SLOT_OF = {
    "Goalkeeper": "POR",
    "Centre-Back": "DC",
    "Sweeper": "DC",
    "Right-Back": "TD",
    "Right Midfield": "TD",  # in Serie A usually a wing-back in a back three
    "Left-Back": "TS",
    "Left Midfield": "TS",
    "Defensive Midfield": "CC",
    "Central Midfield": "CC",
    "Attacking Midfield": "TRQ",
    "Second Striker": "TRQ",
    "Left Winger": "ALI",
    "Right Winger": "ALI",
    "Centre-Forward": "ATT",
    "Defender": "DC",
    "Midfield": "CC",
    "midfield": "CC",
    "Attack": "ATT",
}
_SLOT_OF_RUOLO = {"POR": "POR", "DIF": "DC", "CEN": "CC", "ATT": "ATT"}


def slot_of(position: pd.Series) -> pd.Series:
    """Slot of each Transfermarkt position (NaN if unknown)."""
    return position.map(_SLOT_OF)


def best_slot(*candidates: pd.Series, ruolo: pd.Series | None = None) -> pd.Series:
    """First known slot among several position columns, falling back to the broad role."""
    out = pd.Series(pd.NA, index=candidates[0].index, dtype="object")
    for position in candidates:
        out = out.fillna(slot_of(position))
    if ruolo is not None:
        out = out.fillna(ruolo.map(_SLOT_OF_RUOLO))
    return out
