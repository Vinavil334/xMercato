"""xMercato: market page. Needs of each club and candidates for each position.

Reads the tables written by ``xmercato mercato suggerisci`` (folder ``mercato/``).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from xmercato.ingest.football_data_org import ATTRIBUTION
from xmercato.recommend.slots import LABELS

FOLDER = Path(__file__).resolve().parents[1] / "mercato"
TM_URL = "https://www.transfermarkt.it/-/profil/spieler/{}"
SHOWN = 15  # candidates listed after the filters


@st.cache_data
def load(tag: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    needs = pd.read_csv(FOLDER / f"fabbisogni_{tag}.csv")
    candidates = pd.read_csv(FOLDER / f"candidati_{tag}.csv")
    return needs, candidates


def available_windows() -> list[str]:
    tags = [p.stem.removeprefix("fabbisogni_") for p in FOLDER.glob("fabbisogni_*.csv")]
    return sorted(tags, key=lambda t: (t.split("_")[-1], t.startswith("estate")), reverse=True)


def window_label(tag: str) -> str:
    window, year = tag.rsplit("_", 1)
    return f"{window.capitalize()} {year}"


def needs_table(needs: pd.DataFrame) -> None:
    table = pd.DataFrame(
        {
            "Ruolo": needs["slot"].map(LABELS),
            "Urgenza": needs["punteggio"],
            "Perché": needs["motivo"],
            "Titolari attuali": needs["titolari_nomi"].fillna(""),
            "In rosa": needs["giocatori"],
            "Servono": needs["servono"],
            "Valore titolari": needs["valore_titolari"],
        }
    ).set_index("Ruolo")
    top = max(1.0, float(needs["punteggio"].max()))
    st.dataframe(
        table,
        width="stretch",
        height=35 * (len(table) + 1) + 3,
        column_config={
            "Urgenza": st.column_config.ProgressColumn(
                format="%.2f", min_value=0, max_value=top,
                help="Somma pesata di profondità, qualità, età e contratti (vedi sotto)",
            ),
            "Perché": st.column_config.TextColumn(width="large"),
            "In rosa": st.column_config.NumberColumn(help="Giocatori del ruolo nella rosa verificata"),
            "Servono": st.column_config.NumberColumn(
                help="Un ricambio per ogni titolare del modulo usato l'anno scorso; tre portieri"
            ),
            "Valore titolari": st.column_config.NumberColumn(
                format="%.1f mln", help="Media (geometrica) del valore dei titolari più probabili"
            ),
        },
    )  # fmt: skip


def candidates_table(candidates: pd.DataFrame) -> None:
    table = pd.DataFrame(
        {
            "#": candidates["rango"],
            "Giocatore": candidates["giocatore"],
            "Probabilità": 100 * candidates["probabilita"],
            "Ruolo previsto": candidates["ruolo_previsto"],
            "Età": candidates["eta"],
            "Club": candidates["club_attuale"],
            "Campionato 25/26": candidates["campionato_2025_26"],
            "Valore": candidates["valore_mln"],
            "Minuti 25/26": 100 * candidates["minuti_quota"],
            "Gol": candidates["gol"],
            "Assist": candidates["assist"],
            "Contratto": candidates["scadenza"].replace("nan", ""),
            "Scheda": candidates["tm_id"].map(TM_URL.format),
        }
    ).set_index("#")
    st.dataframe(
        table,
        width="stretch",
        height=35 * (len(table) + 1) + 3,
        column_config={
            "Età": st.column_config.NumberColumn(format="%.0f"),
            "Valore": st.column_config.NumberColumn(format="%.1f mln", help="Transfermarkt, luglio 2026"),
            "Minuti 25/26": st.column_config.ProgressColumn(
                format="%.0f%%", min_value=0, max_value=100,
                help="Quota dei minuti di campionato della sua squadra giocati nel 2025/26",
            ),
            "Ruolo previsto": st.column_config.TextColumn(
                help="Rispetto al valore dei titolari attuali del ruolo: titolare se vale almeno "
                "quanto loro, rotazione se almeno la metà, altrimenti riserva",
            ),
            "Probabilità": st.column_config.NumberColumn(
                format="%.1f%%",
                help="Stima della probabilità che il club lo prenda in questa finestra, "
                "da come hanno comprato i club di Serie A dal 2019. Non dice se sarebbe un buon acquisto",
            ),
            "Scheda": st.column_config.LinkColumn(display_text="Transfermarkt"),
        },
    )  # fmt: skip


st.title("Mercato")
tags = available_windows()
if not tags:
    st.error("Mancano i file in `mercato/`: generali con `uv run xmercato mercato suggerisci`.")
    st.stop()

with st.sidebar:
    st.header("Finestra")
    tag = st.selectbox("Finestra di mercato", tags, format_func=window_label)
needs, candidates = load(tag)

club = st.selectbox("Squadra", sorted(needs["club"].unique()), key="club")
club_needs = needs[needs["club"] == club].sort_values("rango")

st.subheader(f"Dove la rosa è più debole · {window_label(tag)}")
needs_table(club_needs)
notes = []
if "risultati_al" in club_needs and str(club_needs["risultati_al"].iloc[0]) not in ("", "nan"):
    day = pd.Timestamp(club_needs["risultati_al"].iloc[0]).strftime("%d/%m/%Y")
    notes.append(f"Rendimento della stagione calcolato sui risultati fino al {day}.")
if "marcatori" in club_needs and bool(club_needs["marcatori"].iloc[0]):
    notes.append(f"Gol e assist degli attaccanti: {ATTRIBUTION}.")
notes.append(
    "Più che una previsione è una lettura della rosa: dei segnali, solo il rendimento dei "
    "reparti si è visto anche negli acquisti veri delle finestre passate (vedi sotto)."
)
st.caption(" ".join(notes))

st.subheader("Candidati")
left, middle, right, abroad = st.columns([2, 1, 1, 1], vertical_alignment="bottom")
order = list(club_needs["slot"])
slot = left.selectbox(
    "Ruolo",
    order,
    format_func=lambda s: f"{LABELS[s]} (urgenza {order.index(s) + 1}ª)",
    key=f"slot_{club}",
)
here = candidates[(candidates["club"] == club) & (candidates["slot"] == slot)]
max_age = middle.slider("Età massima", 17, 40, 40, key="max_age")
max_value = right.number_input(
    "Valore massimo (mln)", 0.0, 300.0, float(max(1.0, here["valore_mln"].max())), step=1.0
)
only_abroad = abroad.toggle(
    "Solo dall'estero", key="abroad", help="Giocatori che non giocano in Serie A"
)
shown = here[(here["eta"].fillna(0) <= max_age) & (here["valore_mln"] <= max_value)]
if only_abroad:
    shown = shown[shown["estero"]]
shown = shown.head(SHOWN)
if shown.empty:
    st.info("Nessun candidato con questi filtri.")
else:
    candidates_table(shown)

with st.expander("Come funziona, quanto è affidabile, cosa non fa"):
    st.markdown(
        """
- **Fabbisogni.** Per ogni ruolo: quanti giocatori ci sono rispetto a quanti ne servono col modulo
  usato l'anno scorso (un ricambio per titolare, tre portieri); quanto valgono i titolari rispetto a
  un titolare tipico della squadra, confrontato col distacco che c'è di solito nelle altre squadre;
  età e contratti in scadenza; **rendimento della stagione**.
- **Rendimento.** Gol fatti e subiti finora contro quelli che il modello della classifica si
  aspettava a inizio stagione, dati gli avversari incontrati: se l'attacco segna meno del previsto
  sale l'urgenza di centravanti, esterni e trequartisti; se la difesa subisce di più, quella di
  centrali, portiere e terzini. Quando ci sono anche i marcatori (football-data.org), conta pure
  quanti gol e assist stanno facendo gli attaccanti titolari rispetto a giocatori di pari ruolo e
  valore.
- **Verifica.** Il rendimento è l'unico segnale che si vede negli acquisti veri: dal 2019, a gennaio
  ha preso un centravanti il 50% delle squadre il cui attacco era molto sotto le attese, contro il
  24% di quelle molto sopra; un difensore centrale il 63% di quelle con la difesa molto sotto, contro
  il 35%. Profondità e qualità della rosa invece non prevedono dove compra un club.
- **Candidati.** Tutti i giocatori visti nel 2025/26 in 14 campionati europei (Serie A compresa).
  La probabilità viene da un modello addestrato sugli acquisti dei club di Serie A dal 2019: conta
  soprattutto il prezzo rispetto al livello del club, poi età, esperienza in Serie A, minuti giocati,
  nazionalità e rapporti tra i due club.
- **Verifica dei candidati.** Sulle finestre 2023–2025 il 18% degli acquisti veri era tra i primi 10
  della lista del suo ruolo (su circa 1.200 candidati) e il 43% tra i primi 50. Scegliendo i giocatori
  col valore più vicino a quello della squadra: 5% e 24%.
- **Cosa non fa.** Non vede infortuni e voti in pagella. Non dice se l'acquisto sarebbe buono: quella stima arriva con le proiezioni dei
  giocatori. Non vede Serie B, Sudamerica e gli altri campionati senza statistiche nel dataset (circa
  un acquisto su tre arriva da lì). Valori e club sono fermi a luglio 2026, statistiche al 2025/26.
"""
    )
st.caption(
    "Dati: [Transfermarkt](https://www.transfermarkt.it) tramite il dataset pubblico "
    "[transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets) (CC0) e rose "
    "verificate a mano. Sono stime per divertimento, non consigli."
)
