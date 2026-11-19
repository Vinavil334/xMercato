"""xMercato: market page. Needs, squad, injuries and candidates of each club.

Reads the tables written by ``xmercato mercato suggerisci`` (folder ``mercato/``) and the
hand-kept injury list (``rose/indisponibili_*.csv``). The needs are recomputed here from
the saved pieces, so that a change to the injury list shows at once. Changes stay in the
browser session; the owner can save them to the repository (see docs/DATI.md).
"""

from __future__ import annotations

import hmac
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from xmercato import publish
from xmercato.ingest.football_data_org import ATTRIBUTION
from xmercato.recommend import availability, market
from xmercato.recommend.slots import LABELS

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "mercato"
TM_URL = "https://www.transfermarkt.it/-/profil/spieler/{}"
SHOWN = 15  # candidates listed after the filters
EDITED = "modifica dall'app"


@st.cache_data
def load(tag: str) -> tuple[market.NeedParts, pd.DataFrame, dict]:
    parts = market.NeedParts.load(FOLDER, tag)
    candidates = pd.read_csv(FOLDER / f"candidati_{tag}.csv")
    info_path = FOLDER / f"info_{tag}.json"
    info = json.loads(info_path.read_text()) if info_path.exists() else {}
    return parts, candidates, info


def absences_path(info: dict) -> Path | None:
    path = info.get("indisponibili")
    return ROOT / path if path and (ROOT / path).exists() else None


@st.cache_data
def read_absences(path: str | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame(columns=availability.COLUMNS).astype(
            {"rientro_stimato": "datetime64[ns]", "aggiornato": "datetime64[ns]"}
        )
    return availability.read(path)


@st.cache_data
def compute_needs(
    tag: str, window: str, opens: str, absences: pd.DataFrame, today: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    parts, _, _ = load(tag)
    return market.needs_from_parts(
        parts, window, pd.Timestamp(opens), absences, today=pd.Timestamp(today)
    )


def available_windows() -> list[str]:
    tags = [p.stem.removeprefix("rosa_") for p in FOLDER.glob("rosa_*.csv")]
    return sorted(tags, key=lambda t: (t.split("_")[-1], t.startswith("estate")), reverse=True)


def window_label(tag: str) -> str:
    window, year = tag.rsplit("_", 1)
    return f"{window.capitalize()} {year}"


def day(value: str) -> str:
    return pd.Timestamp(value).strftime("%d/%m/%Y")


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
                help="Somma pesata di profondità, qualità, età, contratti, rendimento e infortuni (vedi sotto)",
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
            "Stato": candidates["stato"],
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


def squad_table(squad: pd.DataFrame, absences: pd.DataFrame) -> None:
    back = absences.set_index("giocatore")["rientro"] if len(absences) else pd.Series(dtype=str)
    table = pd.DataFrame(
        {
            "Giocatore": squad["giocatore"],
            "Ruolo": squad["slot"].map(LABELS),
            "Età": squad["eta"],
            "Valore": squad["valore"],
            "Contratto": squad["scadenza"].fillna("").astype(str).str[:10],
            "Tipo": squad["tipo"].fillna("").str.replace("_", " "),
            "Stato": squad["stato"],
            "Rientro": squad["giocatore"].map(back).fillna(""),
        }
    )
    order = {slot: k for k, slot in enumerate(LABELS)}
    table = table.assign(_o=squad["slot"].map(order)).sort_values(
        ["_o", "Valore"], ascending=[True, False]
    )
    st.dataframe(
        table.drop(columns="_o"),
        hide_index=True,
        width="stretch",
        height=35 * (len(table) + 1) + 3,
        column_config={
            "Età": st.column_config.NumberColumn(format="%.0f"),
            "Valore": st.column_config.NumberColumn(format="%.1f mln"),
        },
    )


def edit_absences(club: str, squad: pd.DataFrame, all_absences: pd.DataFrame) -> pd.DataFrame:
    """Editor of the club's injuries; returns the whole list with this club's rows replaced."""
    mine = all_absences[all_absences["club"] == club]
    shown = pd.DataFrame(
        {
            "Giocatore": mine["giocatore"],
            "Problema": mine["problema"],
            "Rientro": mine["rientro"],
            "Rientro stimato": pd.to_datetime(mine["rientro_stimato"]).dt.date,
            "Fonte": mine["fonte"],
        }
    ).reset_index(drop=True)
    edited = st.data_editor(
        shown,
        key=f"editor_{club}",
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        column_config={
            "Giocatore": st.column_config.SelectboxColumn(
                options=sorted(squad["giocatore"]), required=True
            ),
            "Problema": st.column_config.TextColumn(help="In breve, per esempio: muscolare, crociato"),
            "Rientro": st.column_config.TextColumn(help="Come lo dice la notizia, per esempio: dicembre"),
            "Rientro stimato": st.column_config.DateColumn(
                format="DD/MM/YYYY",
                help="Data usata nel calcolo: chi rientra dopo la chiusura della finestra non conta "
                "nella rosa. Vuota se non si sa",
            ),
            "Fonte": st.column_config.LinkColumn(display_text="notizia"),
        },
    )  # fmt: skip
    edited = edited.dropna(subset=["Giocatore"])
    edited = edited[edited["Giocatore"].astype(str).str.len() > 0]
    today = pd.Timestamp.today().normalize()
    rows = pd.DataFrame(
        {
            "club": club,
            "giocatore": edited["Giocatore"].astype(str),
            "problema": edited["Problema"].fillna("").astype(str),
            "rientro": edited["Rientro"].fillna("").astype(str),
            "rientro_stimato": pd.to_datetime(edited["Rientro stimato"], errors="coerce"),
            "fonte": edited["Fonte"].fillna("").astype(str).replace("", EDITED),
            "aggiornato": today,
        }
    )

    # Unchanged rows keep their original date of update.
    def signature(row: pd.Series) -> tuple:
        when = pd.to_datetime(row["rientro_stimato"], errors="coerce")
        return (
            row["problema"],
            row["rientro"],
            row["fonte"],
            "" if pd.isna(when) else str(when.date()),
        )

    before = {r["giocatore"]: r for _, r in mine.iterrows()}
    for i, row in rows.iterrows():
        old = before.get(row["giocatore"])
        if old is not None and signature(old) == signature(row):
            rows.loc[i, "aggiornato"] = old["aggiornato"]
    others = all_absences[all_absences["club"] != club]
    return pd.concat([others, rows], ignore_index=True)[availability.COLUMNS]


def save_box(absences: pd.DataFrame, path: Path | None, changed: bool) -> None:
    left, right = st.columns(2)
    left.download_button(
        "Scarica l'elenco (CSV)",
        availability.to_csv(absences),
        file_name=path.name if path else "indisponibili.csv",
        mime="text/csv",
        width="stretch",
    )
    secrets = {}
    try:
        secrets = dict(st.secrets.get("github", {}))
    except Exception:  # no secrets file: saving is simply not offered
        pass
    if not (secrets.get("token") and secrets.get("password") and path is not None):
        right.caption(
            "Le modifiche valgono solo per te finché non ricarichi la pagina. Per salvarle per "
            "tutti serve la configurazione descritta in docs/DATI.md."
        )
        return
    with right.popover("Salva per tutti", disabled=not changed, width="stretch"):
        password = st.text_input("Password", type="password", key="save_password")
        if st.button("Salva nel repository", type="primary", key="save_button"):
            if not hmac.compare_digest(password, str(secrets["password"])):
                st.error("Password sbagliata.")
                return
            relative = path.relative_to(ROOT).as_posix()
            url = publish.save_file(
                secrets.get("repo", "Vinavil334/xMercato"),
                relative,
                availability.to_csv(absences),
                f"Infortunati: modifica dall'app del {pd.Timestamp.today():%d/%m/%Y}",
                secrets["token"],
                secrets.get("branch", "main"),
            )
            st.success(f"Salvato. L'app si aggiorna da sola in un paio di minuti. [Commit]({url})")


# --------------------------------------------------------------------------------- page

st.title("Mercato")
tags = available_windows()
if not tags:
    st.error("Mancano i file in `mercato/`: generali con `uv run xmercato mercato suggerisci`.")
    st.stop()

with st.sidebar:
    st.header("Finestra")
    tag = st.selectbox("Finestra di mercato", tags, format_func=window_label)
parts, candidates, info = load(tag)
window = info.get("finestra", tag.rsplit("_", 1)[0])
opens = info.get("apertura", f"{tag.rsplit('_', 1)[1]}-01-02")
path = absences_path(info)

# The injury list lives in the session, so that edits survive reruns.
key = f"assenze_{tag}"
if key not in st.session_state:
    st.session_state[key] = read_absences(str(path) if path else None)
original = read_absences(str(path) if path else None)

club = st.selectbox("Squadra", sorted(parts.squad["club"].unique()), key="club")
squad_club = parts.squad[parts.squad["club"] == club]

today = min(pd.Timestamp(opens), pd.Timestamp.today().normalize())
tab_needs, tab_squad, tab_candidates = st.tabs(["Fabbisogni", "Rosa e infortuni", "Candidati"])

with tab_squad:
    st.markdown(
        "**Infortunati** · aggiungi una riga in fondo, cambia una cella o seleziona una riga "
        "per eliminarla: fabbisogni e candidati si ricalcolano subito."
    )
    absences = edit_absences(club, squad_club, st.session_state[key])
    changed = availability.to_csv(absences) != availability.to_csv(original)
    st.session_state[key] = absences

needs, squad = compute_needs(tag, window, opens, st.session_state[key], today.isoformat())
club_needs = needs[needs["club"] == club].sort_values("rango")

with tab_squad:
    if changed:
        st.info("Elenco modificato: fabbisogni e candidati tengono già conto delle modifiche.")
        if st.button("Annulla le modifiche", key="reset"):
            st.session_state[key] = original
            st.session_state.pop(f"editor_{club}", None)
            st.rerun()
    save_box(st.session_state[key], path, changed)
    st.markdown(f"**Rosa · {len(squad_club)} giocatori**")
    club_absences = st.session_state[key][st.session_state[key]["club"] == club]
    squad_table(squad[squad["club"] == club], club_absences)

with tab_needs:
    st.subheader(f"Dove la rosa è più debole · {window_label(tag)}")
    needs_table(club_needs)
    notes = []
    if info.get("risultati_al"):
        notes.append(
            f"Rendimento della stagione calcolato sui risultati fino al {day(info['risultati_al'])}."
        )
    if info.get("indisponibili_al"):
        notes.append(
            f"Infortunati aggiornati al {day(info['indisponibili_al'])}"
            + (", con le tue modifiche" if changed else "")
            + ": chi resta fuori oltre la finestra non conta nella rosa."
        )
    if info.get("marcatori"):
        notes.append(f"Gol e assist degli attaccanti: {ATTRIBUTION}.")
    notes.append(
        "Più che una previsione è una lettura della rosa: dei segnali, solo il rendimento dei "
        "reparti si è visto anche negli acquisti veri delle finestre passate (vedi sotto)."
    )
    st.caption(" ".join(notes))

with tab_candidates:
    left, middle, right, abroad = st.columns([2, 1, 1, 1], vertical_alignment="bottom")
    order = list(club_needs["slot"])
    slot = left.selectbox(
        "Ruolo",
        order,
        format_func=lambda s: f"{LABELS[s]} (urgenza {order.index(s) + 1}ª)",
        key=f"slot_{club}",
    )
    here = candidates[(candidates["club"] == club) & (candidates["slot"] == slot)].copy()
    note, out = availability.candidate_status(
        here, st.session_state[key], today, market.window_end(pd.Timestamp(opens), window)
    )
    here["stato"] = note
    max_age = middle.slider("Età massima", 17, 40, 40, key="max_age")
    max_value = right.number_input(
        "Valore massimo (mln)", 0.0, 300.0, float(max(1.0, here["valore_mln"].max())), step=1.0
    )
    only_abroad = abroad.toggle(
        "Solo dall'estero", key="abroad", help="Giocatori che non giocano in Serie A"
    )
    shown = here[~out & (here["eta"].fillna(0) <= max_age) & (here["valore_mln"] <= max_value)]
    if only_abroad:
        shown = shown[shown["estero"]]
    shown = shown.head(SHOWN)
    if shown.empty:
        st.info("Nessun candidato con questi filtri.")
    else:
        candidates_table(shown)
    if out.any():
        names = ", ".join(here.loc[out, "giocatore"])
        st.caption(f"Tolti perché infortunati oltre la finestra: {names}.")

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
- **Infortuni.** Da un elenco tenuto a mano dai bollettini pubblici, modificabile nella scheda
  *Rosa e infortuni*. Chi resta fuori oltre la chiusura della finestra non conta nella rosa; chi è
  infortunato non viene giudicato su gol e assist; tra i candidati, chi è fuori per la finestra sparisce.
- **Cosa non fa.** Non vede i voti in pagella. Non dice se l'acquisto sarebbe buono: quella stima arriva con le proiezioni dei
  giocatori. Non vede Serie B, Sudamerica e gli altri campionati senza statistiche nel dataset (circa
  un acquisto su tre arriva da lì). Valori e club sono fermi a luglio 2026, statistiche al 2025/26.
"""
    )
st.caption(
    "Dati: [Transfermarkt](https://www.transfermarkt.it) tramite il dataset pubblico "
    "[transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets) (CC0) e rose "
    "verificate a mano. Sono stime per divertimento, non consigli."
)
