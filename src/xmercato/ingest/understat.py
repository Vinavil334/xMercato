"""Match-level xG from the public archive of Understat shots.

The `worldfootballR_data <https://github.com/JaseZiv/worldfootballR_data>`_ repository (now
archived) publishes every Understat shot of the Big 5 leagues as R data files. Summing the
xG of each team's shots gives the match xG that Understat shows. For Serie A the archive
covers 2014/15 to 2023/24 and the first half of 2024/25.

Data from understat.com: credit the source wherever it is shown.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SERIE_A_SHOTS_URL = (
    "https://raw.githubusercontent.com/JaseZiv/worldfootballR_data/master/"
    "data/understat_shots/serie_a_shot_data.rds"
)


def read_shots(path: str | Path) -> pd.DataFrame:
    """Read the shots archive (an ``.rds`` file). Needs the optional ``rdata`` package."""
    try:
        import rdata
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise ImportError("Reading the archive needs `uv sync --extra storico`") from error
    parsed = rdata.parser.parse_file(Path(path))
    converted = rdata.conversion.convert(parsed, default_encoding="latin1")
    df = converted if isinstance(converted, pd.DataFrame) else next(iter(converted.values()))
    df = pd.DataFrame(df)
    df.columns = [str(c) for c in df.columns]
    return df


def match_xg(shots: pd.DataFrame) -> pd.DataFrame:
    """One row per match: date, teams, final score and each side's total xG."""
    required = {"match_id", "season", "date", "home_team", "away_team", "home_goals",
                "away_goals", "h_a", "xG"}  # fmt: skip
    missing = required - set(shots.columns)
    if missing:
        raise ValueError(f"Not an Understat shots table, missing {sorted(missing)}")
    side_of_shot = shots["h_a"]
    if "home_away" in shots.columns:  # the archive switched column from 2022/23 on
        side_of_shot = side_of_shot.fillna(shots["home_away"])
    side_of_shot = side_of_shot.astype("string").str.lower().str.slice(0, 1)  # home -> h
    shots = shots.assign(
        xG=pd.to_numeric(shots["xG"], errors="coerce").fillna(0.0), h_a=side_of_shot
    )
    side = shots.pivot_table(index="match_id", columns="h_a", values="xG", aggfunc="sum")
    side = side.reindex(columns=["h", "a"], fill_value=0.0).fillna(0.0)
    info = shots.groupby("match_id")[
        ["season", "date", "home_team", "away_team", "home_goals", "away_goals"]
    ].first()
    out = info.join(side).reset_index()
    return pd.DataFrame(
        {
            "season": out["season"].astype(int),
            "date": pd.to_datetime(out["date"].astype(str).str.slice(0, 10)),
            "home": out["home_team"].astype(str),
            "away": out["away_team"].astype(str),
            "home_goals": out["home_goals"].astype(int),
            "away_goals": out["away_goals"].astype(int),
            "home_xg": out["h"].round(4),
            "away_xg": out["a"].round(4),
            "understat_id": out["match_id"].astype(int),
        }
    ).sort_values(["date", "understat_id"], kind="stable", ignore_index=True)
