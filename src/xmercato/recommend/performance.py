"""How a club's players are doing this season, as an input to its squad needs.

Two signals, both measured against what was expected before the season:

- **Departments** (from results only, every club): goals scored and conceded so far,
  against what the league-table model expected from the pre-season strengths and the
  opponents faced. Scoring less than expected raises the need in attack (centre-forward
  first, then wingers and attacking midfielders); conceding more raises it in defence.
  Both are corrected for the scoring level of the whole league this season.
- **Attacking players** (from the football-data.org scorers, when a token is available):
  goals plus assists per match of the likely starters up front, against what players of
  the same position and market value produced in Serie A since 2018.

Each signal is a z-score (how many standard deviations below expectation, Poisson
approximation), turned into a 0-1 "form" need: 0 down to expectation, 1 at three standard
deviations below. A slot takes the stronger of the two.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from xmercato.models import forecast
from xmercato.rose_sync import normalise, similarity

# How much each slot feels a department that scores or concedes worse than expected.
ATTACK_SLOTS = {"ATT": 1.0, "ALI": 0.7, "TRQ": 0.7}
DEFENCE_SLOTS = {"DC": 1.0, "POR": 0.7, "TD": 0.5, "TS": 0.5}
FULL_SCALE = 3.0  # z-score that counts as the largest form need
MIN_EXPECTED = 1.0  # below this many expected goals+assists a player's numbers say nothing


def _need(z: float | np.ndarray) -> float | np.ndarray:
    return np.clip(-np.asarray(z, dtype=float), 0, FULL_SCALE) / FULL_SCALE


# --------------------------------------------------------------------------- departments


def team_form(
    history: pd.DataFrame,
    season: int,
    config: forecast.ModelConfig = forecast.GOALS,
) -> pd.DataFrame:
    """Goals scored and conceded so far against the pre-season expectation of each team."""
    current = history[history["season"] == season]
    teams = sorted(set(current["home"]) | set(current["away"]))
    strengths = forecast.fit_as_of(history, season, current["date"].min(), config, teams)
    index = {t: k for k, t in enumerate(strengths.teams)}
    h = current["home"].map(index).to_numpy()
    a = current["away"].map(index).to_numpy()
    s = strengths
    lam_h = np.exp(s.mu + s.home_adv + s.attack[h] - s.defence[a])
    lam_a = np.exp(s.mu + s.attack[a] - s.defence[h])
    # This season's league may score more or less than the model's past seasons.
    level = (current["home_goals"].sum() + current["away_goals"].sum()) / (lam_h + lam_a).sum()

    rows = []
    for team in teams:
        home = (current["home"] == team).to_numpy()
        away = (current["away"] == team).to_numpy()
        scored = (
            current["home_goals"].to_numpy()[home].sum()
            + current["away_goals"].to_numpy()[away].sum()
        )
        conceded = (
            current["away_goals"].to_numpy()[home].sum()
            + current["home_goals"].to_numpy()[away].sum()
        )
        exp_scored = level * (lam_h[home].sum() + lam_a[away].sum())
        exp_conceded = level * (lam_a[home].sum() + lam_h[away].sum())
        rows.append(
            {
                "club": team,
                "partite": int(home.sum() + away.sum()),
                "gol_fatti": int(scored),
                "gol_fatti_attesi": round(exp_scored, 1),
                "gol_subiti": int(conceded),
                "gol_subiti_attesi": round(exp_conceded, 1),
                "z_attacco": (scored - exp_scored) / np.sqrt(max(exp_scored, 1e-9)),
                "z_difesa": (exp_conceded - conceded) / np.sqrt(max(exp_conceded, 1e-9)),
            }
        )
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------ players


def fit_rates(player_seasons: pd.DataFrame, min_games: int = 5) -> dict[str, tuple[float, float]]:
    """Goals+assists per Serie A appearance by slot: log rate = a + b * log(value in millions).

    ``player_seasons`` needs ``slot``, ``competition_id``, ``partite``, ``gol``, ``assist`` and
    ``valore_inizio``. Poisson regression with the appearances as exposure.
    """
    rows = player_seasons[
        (player_seasons["competition_id"] == "IT1")
        & (player_seasons["partite"] >= min_games)
        & player_seasons["valore_inizio"].notna()
    ]
    rates = {}
    for slot in [*ATTACK_SLOTS, "CC"]:
        r = rows[rows["slot"] == slot]
        if len(r) < 30:
            continue
        x = np.log((r["valore_inizio"] / 1e6).clip(lower=0.1)).to_numpy()
        y = (r["gol"] + r["assist"]).to_numpy(dtype=float)
        exposure = np.log(r["partite"].to_numpy(dtype=float))

        def loss(b: np.ndarray, x=x, y=y, exposure=exposure) -> tuple[float, np.ndarray]:
            eta = b[0] + b[1] * x + exposure
            mu = np.exp(eta)
            return float((mu - y * eta).sum()), np.array([(mu - y).sum(), ((mu - y) * x).sum()])

        b = minimize(loss, np.array([-1.5, 0.3]), jac=True, method="L-BFGS-B").x
        rates[slot] = (float(b[0]), float(b[1]))
    return rates


def expected_rate(rates: dict[str, tuple[float, float]], slot: str, value: float) -> float:
    a, b = rates[slot]
    return float(np.exp(a + b * np.log(max(value, 0.1))))


def match_scorers(scorers: pd.DataFrame, squad: pd.DataFrame, threshold: float = 0.85) -> pd.Series:
    """For each squad row, the index of the same player in ``scorers`` (NaN if none).

    Only players of the same club are compared; ``scorers.squadra`` must already use the
    squad's club names. Names are matched in full first; failing that, by the surname when
    it is unique in both lists ("R. Kolo Muani").
    """
    out = pd.Series(np.nan, index=squad.index)

    def surname(name: str) -> str:
        parts = normalise(name).split()
        return parts[-1] if parts else ""

    for club, players in squad.groupby("club"):
        candidates = scorers[scorers["squadra"] == club]
        if candidates.empty:
            continue
        their = candidates["giocatore"].map(surname)
        ours = players["giocatore"].map(surname)
        for i, name in players["giocatore"].items():
            scores = candidates["giocatore"].map(lambda s, name=name: similarity(name, s))
            if scores.max() >= threshold:
                out[i] = scores.idxmax()
            elif (their == ours[i]).sum() == 1 and (ours == ours[i]).sum() == 1 and ours[i]:
                out[i] = their.index[their == ours[i]][0]
    return out


def player_form(
    squad: pd.DataFrame,
    usage: pd.DataFrame,
    scorers: pd.DataFrame,
    rates: dict[str, tuple[float, float]],
    team_games: pd.Series,
) -> pd.DataFrame:
    """Goals+assists of the likely attacking starters against expectation.

    A starter missing from the scorers list has no goal and no assist: we do not know how
    many matches he played, so half of his team's matches are assumed (he may have been
    injured, which is a need too).
    """
    starters_used = usage.set_index(["club", "slot"])["titolari"]
    link = match_scorers(scorers, squad)
    rows = []
    for (club, slot), players in squad.groupby(["club", "slot"]):
        if slot not in ATTACK_SLOTS or slot not in rates:
            continue
        n = max(1, round(float(starters_used.get((club, slot), 0.0))))
        for i, player in players.sort_values("valore", ascending=False).head(n).iterrows():
            rate = expected_rate(rates, slot, float(player["valore"]))
            if pd.notna(link[i]):
                row = scorers.loc[link[i]]
                games, made, listed = int(row["partite"]), int(row["gol"] + row["assist"]), True
            else:
                games, made, listed = int(0.5 * team_games.get(club, 0)), 0, False
            expected = rate * games
            if expected < MIN_EXPECTED:
                continue
            rows.append(
                {
                    "club": club,
                    "slot": slot,
                    "giocatore": player["giocatore"],
                    "partite": games if listed else None,
                    "gol_assist": made,
                    "attesi": round(expected, 1),
                    "z": (made - expected) / np.sqrt(expected),
                    "nei_marcatori": listed,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "club",
            "slot",
            "giocatore",
            "partite",
            "gol_assist",
            "attesi",
            "z",
            "nei_marcatori",
        ],
    )


# ------------------------------------------------------------------------------ together


def _department_note(row: pd.Series, attack: bool) -> str:
    games = row["partite"]
    if attack:
        scored, expected = row["gol_fatti"], row["gol_fatti_attesi"]
        return f"attacco: {scored} gol in {games} partite, attesi {expected:.0f}"
    conceded, expected = row["gol_subiti"], row["gol_subiti_attesi"]
    return f"difesa: {conceded} gol subiti in {games} partite, attesi {expected:.0f}"


def _player_note(row: pd.Series) -> str:
    if row["nei_marcatori"]:
        made, games, expected = row["gol_assist"], row["partite"], row["attesi"]
        return (
            f"{row['giocatore']}: {made} tra gol e assist in {games} partite, attesi {expected:.0f}"
        )
    return f"{row['giocatore']}: nessun gol né assist in campionato"


def form_needs(teams: pd.DataFrame, players: pd.DataFrame | None = None) -> pd.DataFrame:
    """Form need (0-1) of every club and slot, with the reason in Italian."""
    rows = []
    for _, team in teams.iterrows():
        for slot, weight in {**ATTACK_SLOTS, **DEFENCE_SLOTS}.items():
            attack = slot in ATTACK_SLOTS
            z = team["z_attacco"] if attack else team["z_difesa"]
            need = weight * float(_need(z))
            notes = [_department_note(team, attack)] if need > 0.05 else []
            if players is not None and attack:
                here = players[(players["club"] == team["club"]) & (players["slot"] == slot)]
                bad = here[here["z"] < -1]
                if len(here):
                    player_need = float(_need(here["z"]).mean())
                    if player_need > need:
                        need = player_need
                    notes += [_player_note(r) for _, r in bad.iterrows()]
            rows.append(
                {
                    "club": team["club"],
                    "slot": slot,
                    "forma": round(need, 3),
                    "nota_forma": "; ".join(notes),
                }
            )
    return pd.DataFrame(rows)
