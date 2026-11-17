"""Tables of the public Transfermarkt dataset (github.com/dcaribou/transfermarkt-datasets).

Each table is a gzipped CSV, read either from a local folder or from the dataset's public
bucket. Updates of the dataset are paused: the last snapshot is from July 2026.
Only the columns that xMercato uses are checked, so that a schema change upstream fails
here with a clear message instead of deep inside a model.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

BASE_URL = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/{table}.csv.gz"

REQUIRED_COLUMNS = {
    "players": [
        "player_id",
        "name",
        "date_of_birth",
        "position",
        "current_club_id",
        "last_season",
        "contract_expiration_date",
        "market_value_in_eur",
    ],
    "clubs": ["club_id", "name", "domestic_competition_id", "last_season"],
    "transfers": ["player_id", "transfer_date", "to_club_id"],
    "player_valuations": ["player_id", "date", "market_value_in_eur"],
}


def table_url(table: str) -> str:
    return BASE_URL.format(table=table)


def load_table(table: str, source_dir: str | Path | None = None) -> pd.DataFrame:
    """Read one table from ``source_dir/<table>.csv.gz`` or, without a folder, from the bucket."""
    if table not in REQUIRED_COLUMNS:
        raise ValueError(f"Unknown table {table!r}; known: {sorted(REQUIRED_COLUMNS)}")
    source = Path(source_dir) / f"{table}.csv.gz" if source_dir else table_url(table)
    df = pd.read_csv(source, low_memory=False)
    missing = [c for c in REQUIRED_COLUMNS[table] if c not in df.columns]
    if missing:
        raise ValueError(
            f"Table {table!r} lacks columns {missing}. The upstream schema may have changed; "
            f"columns found: {list(df.columns)}"
        )
    return df


def load_all(source_dir: str | Path | None = None) -> dict[str, pd.DataFrame]:
    return {table: load_table(table, source_dir) for table in REQUIRED_COLUMNS}
