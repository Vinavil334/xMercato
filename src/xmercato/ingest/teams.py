"""One name per club across sources.

The canonical name is the one football-data.co.uk uses (it is also the name in the squad
files). Other sources are mapped onto it: first through explicit aliases, then by matching
normalised names within the same season, where only twenty candidates exist.
"""

from __future__ import annotations

import re
import unicodedata

# Source name -> canonical name, for names that do not match after normalisation.
ALIASES = {
    "AC Milan": "Milan",
    "Inter Milan": "Inter",
    "Internazionale": "Inter",
    "Parma Calcio 1913": "Parma",
    "Hellas Verona": "Verona",
    "SPAL 2013": "Spal",
    "SPAL": "Spal",
    "Chievo Verona": "Chievo",
    "AS Roma": "Roma",
    "SS Lazio": "Lazio",
    # football-data.org
    "FC Internazionale Milano": "Inter",
    "Hellas Verona FC": "Verona",
}


def normalise(name: str) -> str:
    text = unicodedata.normalize("NFKD", str(name))
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"\b(ac|as|ss|ssc|us|fc|cfc|calcio|bc|1907|1909|1913|2013|cf)\b", " ", text)
    return re.sub(r"[^a-z]+", " ", text).strip()


def map_names(source_names: set[str], canonical_names: set[str]) -> dict[str, str]:
    """Map each source name onto one canonical name; raises if any is left ambiguous."""
    by_norm = {normalise(c): c for c in canonical_names}
    mapping, missing = {}, []
    for name in sorted(source_names):
        target = ALIASES.get(name) or by_norm.get(normalise(name))
        if target is None:
            # Unique canonical name contained in the source name, or vice versa.
            n = normalise(name)
            hits = [c for k, c in by_norm.items() if k and (k in n or n in k)]
            target = hits[0] if len(hits) == 1 else None
        if target is None or target not in canonical_names:
            missing.append(name)
        else:
            mapping[name] = target
    if missing:
        raise ValueError(f"Could not map team names {missing} onto {sorted(canonical_names)}")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError(f"Two source names map onto the same club: {mapping}")
    return mapping
