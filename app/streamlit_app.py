"""xMercato: interactive league table simulator (level 1).

Run with ``uv run streamlit run app/streamlit_app.py``.

The app only orchestrates: all the modelling lives in the ``xmercato`` package.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

try:
    import xmercato  # noqa: F401
except ModuleNotFoundError:  # running from a checkout where the package is not installed
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import altair as alt
import pandas as pd
import streamlit as st

from xmercato.ingest import football_data
from xmercato.models import poisson
from xmercato.sim import season

SEED = 2026
SAMPLE_LABEL = "2025/26 (completa, inclusa nell'app)"

# One-hue sequential ramp, light to dark. On a dark page it is reversed, so that
# "close to zero" always recedes into the background.
BLUE_RAMP = ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]
HEATMAP_ROW = 26  # pixels per team


# ----------------------------------------------------------------------------- data


def current_season_start(today: date) -> int:
    """Serie A seasons start in August: before that, the 'current' one began last year."""
    return today.year if today.month >= 8 else today.year - 1


@st.cache_data(ttl=3600, show_spinner="Scarico i risultati…")
def load_online(season_start: int) -> pd.DataFrame:
    return football_data.load_results(football_data.serie_a_url(season_start))


@st.cache_data
def load_sample() -> pd.DataFrame:
    return football_data.load_results(football_data.SAMPLE_SEASON)


@st.cache_data(show_spinner="Simulo il campionato…")
def run(
    results: pd.DataFrame,
    teams: tuple[str, ...],
    goals_for: tuple[tuple[str, float], ...],
    goals_against: tuple[tuple[str, float], ...],
    fixed: tuple[tuple[str, str, int, int], ...],
    n_sims: int,
) -> pd.DataFrame:
    """Fit on the real results, apply the scenario, simulate. Cached on every input."""
    strengths = poisson.fit(results, teams=list(teams))
    strengths = strengths.scaled(goals_for=dict(goals_for), goals_against=dict(goals_against))
    fixed_df = pd.DataFrame(fixed, columns=["home", "away", "home_goals", "away_goals"])
    return season.simulate(strengths, results, n_sims=n_sims, seed=SEED, fixed=fixed_df)


# ------------------------------------------------------------------------- scenario


def reset_scenario() -> None:
    st.session_state["mod_teams"] = []
    st.session_state["fixed"] = {}
    for key in list(st.session_state):
        if key.startswith(("gf_", "ga_")):
            del st.session_state[key]


def remove_fixed(pair: tuple[str, str]) -> None:
    st.session_state["fixed"].pop(pair, None)


def strength_controls(teams: list[str]) -> tuple[dict[str, float], dict[str, float]]:
    st.markdown("**Forza delle squadre**")
    chosen = st.multiselect(
        "Squadre da modificare",
        teams,
        key="mod_teams",
        placeholder="Scegli una o più squadre",
        label_visibility="collapsed",
    )
    goals_for, goals_against = {}, {}
    for team in chosen:
        left, right = st.columns(2)
        up = left.slider(f"{team}: gol fatti", -50, 50, 0, 5, format="%+d%%", key=f"gf_{team}")
        down = right.slider(f"{team}: gol subiti", -50, 50, 0, 5, format="%+d%%", key=f"ga_{team}")
        if up:
            goals_for[team] = 1 + up / 100
        if down:
            goals_against[team] = 1 + down / 100
    if not chosen:
        st.caption(
            "Esempio: +10% di gol fatti equivale a un attacco che segna un gol in più ogni dieci."
        )
    return goals_for, goals_against


def fixed_controls(todo: pd.DataFrame) -> dict[tuple[str, str], tuple[int, int]]:
    st.markdown("**Risultati fissati**")
    fixed: dict[tuple[str, str], tuple[int, int]] = st.session_state.setdefault("fixed", {})
    # Drop pins that no longer apply (the date moved and the match has now been played).
    left_to_play = set(zip(todo["home"], todo["away"], strict=True))
    for pair in [p for p in fixed if p not in left_to_play]:
        del fixed[pair]

    options = [pair for pair in zip(todo["home"], todo["away"], strict=True) if pair not in fixed]
    with st.form("fix_result", clear_on_submit=True, border=False):
        match = st.selectbox(
            "Partita ancora da giocare",
            options,
            format_func=lambda pair: f"{pair[0]} – {pair[1]}",
            index=None,
            placeholder="Scegli una partita (casa – trasferta)",
            label_visibility="collapsed",
        )
        left, right, button = st.columns([1, 1, 1.4], vertical_alignment="bottom")
        home_goals = left.number_input("Gol casa", 0, 15, 0)
        away_goals = right.number_input("Gol trasferta", 0, 15, 0)
        if button.form_submit_button("Fissa il risultato", width="stretch") and match:
            fixed[match] = (int(home_goals), int(away_goals))

    for (home, away), (hg, ag) in fixed.items():
        text, button = st.columns([4, 1], vertical_alignment="center")
        text.write(f"{home} – {away} **{hg}-{ag}**")
        button.button("Togli", key=f"rm_{home}_{away}", on_click=remove_fixed, args=((home, away),))
    return fixed


# -------------------------------------------------------------------------- display


def league_table(summary: pd.DataFrame) -> pd.DataFrame:
    table = pd.DataFrame(
        {
            "#": range(1, len(summary) + 1),
            "Squadra": summary.index,
            "PG": summary["played"].to_numpy(),
            "Punti": summary["points"].to_numpy(),
            "Punti attesi": summary["exp_points"].to_numpy(),
            "Scudetto": 100 * summary["p_title"].to_numpy(),
            "Prime 4": 100 * summary["p_top4"].to_numpy(),
            "Retrocessione": 100 * summary["p_relegation"].to_numpy(),
        }
    )
    return table.set_index("#")


def show_table(summary: pd.DataFrame) -> None:
    def share(help_text: str) -> st.column_config.ProgressColumn:
        return st.column_config.ProgressColumn(
            format="%.1f%%", min_value=0, max_value=100, help=help_text
        )

    st.dataframe(
        league_table(summary),
        width="stretch",
        height=35 * (len(summary) + 1) + 3,
        column_config={
            "#": st.column_config.NumberColumn(width=40),
            "Squadra": st.column_config.TextColumn(width=140),
            "PG": st.column_config.NumberColumn(width=60, help="Partite giocate"),
            "Punti": st.column_config.NumberColumn(width=70, help="Punti reali alla data scelta"),
            "Punti attesi": st.column_config.NumberColumn(
                width=110, format="%.1f", help="Media dei punti finali nelle stagioni simulate"
            ),
            "Scudetto": share("Probabilità di finire al primo posto"),
            "Prime 4": share("Probabilità di finire tra le prime quattro"),
            "Retrocessione": share("Probabilità di finire tra le ultime tre"),
        },
    )


def show_changes(summary: pd.DataFrame, baseline: pd.DataFrame) -> None:
    base = baseline.reindex(summary.index)
    delta = pd.DataFrame(
        {
            "Squadra": summary.index,
            "Punti attesi": (summary["exp_points"] - base["exp_points"]).to_numpy(),
            "Scudetto": 100 * (summary["p_title"] - base["p_title"]).to_numpy(),
            "Prime 4": 100 * (summary["p_top4"] - base["p_top4"]).to_numpy(),
            "Retrocessione": 100 * (summary["p_relegation"] - base["p_relegation"]).to_numpy(),
        }
    )
    # Every opponent of a modified team moves a little: keep only the changes worth reading.
    moved = (delta["Punti attesi"].abs() >= 0.5) | (delta.iloc[:, 2:].abs() >= 1.0).any(axis=1)
    delta = delta[moved].sort_values("Punti attesi", ascending=False, key=abs)
    if delta.empty:
        st.caption("Con questo scenario non cambia nulla di apprezzabile.")
        return
    numbers = delta.columns[1:]
    delta[numbers] = delta[numbers].round(1) + 0.0  # the sum turns -0.0 into 0.0
    points = st.column_config.NumberColumn(format="%+.1f")
    st.dataframe(
        delta.set_index("Squadra"),
        width="stretch",
        column_config={
            "Punti attesi": points,
            "Scudetto": st.column_config.NumberColumn(format="%+.1f", help="Punti percentuali"),
            "Prime 4": st.column_config.NumberColumn(format="%+.1f", help="Punti percentuali"),
            "Retrocessione": st.column_config.NumberColumn(
                format="%+.1f", help="Punti percentuali"
            ),
        },
    )
    st.caption(
        "Differenze rispetto alla simulazione senza modifiche: punti attesi in punti, le altre "
        "colonne in punti percentuali. Sono elencate solo le squadre che si spostano di almeno "
        "mezzo punto o di un punto percentuale."
    )


def position_heatmap(table: pd.DataFrame) -> alt.Chart:
    pos_cols = [c for c in table.columns if c.startswith("pos_")]
    long = (
        table[pos_cols]
        .rename(columns=lambda c: int(c.removeprefix("pos_")))
        .rename_axis(columns="Posizione")
        .stack()
        .rename("Probabilità")
        .reset_index()
        .rename(columns={"team": "Squadra"})
    )
    long = long[long["Probabilità"] >= 0.001]  # cells that would show as 0.0% stay empty

    dark = getattr(st.context.theme, "type", "light") == "dark"
    ramp = BLUE_RAMP[::-1] if dark else BLUE_RAMP
    return (
        alt.Chart(long)
        .mark_rect(cornerRadius=2)
        .encode(
            x=alt.X(
                "Posizione:O",
                title="Posizione finale",
                axis=alt.Axis(
                    orient="top", labelAngle=0, ticks=False, domain=False, labelOverlap=False
                ),
                scale=alt.Scale(domain=list(range(1, len(table) + 1)), paddingInner=0.1),
            ),
            y=alt.Y(
                "Squadra:N",
                sort=list(table.index),
                title=None,
                axis=alt.Axis(ticks=False, domain=False, labelOverlap=False, labelLimit=120),
                scale=alt.Scale(paddingInner=0.1),
            ),
            color=alt.Color(
                "Probabilità:Q",
                scale=alt.Scale(range=ramp, domainMin=0),
                legend=alt.Legend(title="Probabilità", format=".0%", orient="bottom"),
            ),
            tooltip=[
                alt.Tooltip("Squadra:N"),
                alt.Tooltip("Posizione:O", title="Posizione finale"),
                alt.Tooltip("Probabilità:Q", format=".1%"),
            ],
        )
        .properties(height=HEATMAP_ROW * len(table))
        .configure_view(strokeWidth=0)
    )


# ----------------------------------------------------------------------------- page


def main() -> None:
    st.set_page_config(page_title="xMercato · Simulatore", page_icon="⚽", layout="wide")
    st.title("Simulatore della classifica")

    live_start = current_season_start(date.today())
    live_label = f"{live_start}/{(live_start + 1) % 100:02d} (in corso)"

    with st.sidebar:
        st.header("Dati")
        choice = st.radio("Stagione", [live_label, SAMPLE_LABEL])
        results = None
        if choice == live_label:
            try:
                results = load_online(live_start)
            except Exception as error:  # network down, file not published yet, format changed
                st.warning(
                    "Non riesco a scaricare la stagione in corso da football-data.co.uk "
                    f"({type(error).__name__}). Uso la stagione 2025/26 inclusa nell'app."
                )
        if results is None or results.empty:
            results = load_sample()

        teams = sorted(set(results["home"]) | set(results["away"]))
        first, last = results["date"].min().date(), results["date"].max().date()
        complete = len(season.remaining_fixtures(results, teams)) == 0
        # A finished season is only interesting from an earlier point: start at the halfway mark.
        default = results["date"].iloc[len(results) // 2].date() if complete else last
        as_of = st.slider(
            "Usa i risultati fino al", first, last, default, format="DD/MM/YYYY",
            help="Sposta indietro la data per vedere come appariva il campionato in quel momento.",
        )  # fmt: skip
        n_sims = st.select_slider("Stagioni simulate", [2_000, 10_000, 20_000], value=10_000)

    played = results[results["date"].dt.date <= as_of].reset_index(drop=True)
    todo = season.remaining_fixtures(played, teams)
    if len(teams) != 20:
        st.warning(
            f"Nei risultati compaiono {len(teams)} squadre invece di 20: "
            "a inizio stagione le squadre che non hanno ancora giocato mancano dalla simulazione."
        )
    st.caption(
        f"Risultati fino al {as_of:%d/%m/%Y}: {len(played)} partite giocate, {len(todo)} da simulare."
    )

    with st.container(border=True):
        head, reset = st.columns([5, 1], vertical_alignment="center")
        head.subheader("Scenario: e se…")
        reset.button("Azzera", on_click=reset_scenario, width="stretch")
        left, right = st.columns(2, gap="large")
        with left:
            goals_for, goals_against = strength_controls(teams)
        with right:
            fixed = fixed_controls(todo)

    args = (played, tuple(teams))
    scenario = (
        tuple(sorted(goals_for.items())),
        tuple(sorted(goals_against.items())),
        tuple((h, a, hg, ag) for (h, a), (hg, ag) in sorted(fixed.items())),
    )
    table = run(*args, *scenario, n_sims)
    summary = season.summarise(table)
    has_scenario = any(scenario)

    if has_scenario:
        st.subheader("Cosa cambia")
        baseline = season.summarise(run(*args, (), (), (), n_sims))
        show_changes(summary, baseline)

    st.subheader("Classifica finale prevista")
    show_table(summary)

    st.subheader("Dove può finire ogni squadra")
    st.altair_chart(position_heatmap(table), width="stretch", height=HEATMAP_ROW * len(table) + 110)
    with st.expander("Le stesse probabilità in tabella"):
        grid = table.filter(like="pos_").rename(columns=lambda c: c.removeprefix("pos_"))
        st.dataframe((100 * grid).round(1), width="stretch")

    with st.expander("Come funziona, e cosa non fa"):
        st.markdown(
            """
- **Modello.** La forza in attacco e in difesa di ogni squadra è stimata dai risultati fino alla data
  scelta, con un modello di Poisson. Le partite rimanenti vengono giocate migliaia di volte.
- **Scenario.** Le modifiche alla forza valgono per tutte le partite rimanenti della squadra. I risultati
  fissati entrano nella classifica finale ma non cambiano la stima della forza.
- **Confronto pulito.** Scenario e simulazione di base usano gli stessi numeri casuali: cambiano solo le
  partite toccate dalle tue modifiche, quindi le differenze non sono rumore.
- **Limiti.** A pari punti decide la differenza reti, non gli scontri diretti. Il modello guarda solo i
  gol di questa stagione: niente xG, infortuni, mercato o calendario delle coppe. A inizio stagione le
  stime sono molto incerte.
"""
        )
    st.caption(
        "Dati: [football-data.co.uk](https://www.football-data.co.uk). "
        "Codice: [github.com/Vinavil334/xMercato](https://github.com/Vinavil334/xMercato). "
        "Sono stime, non consigli per scommesse."
    )


main()
