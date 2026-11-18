# Roadmap

Ipotesi: lavoro nel tempo libero, **5-6 ore a settimana**. Le durate sono stime, non impegni: le fasi 2
e 4 sono quelle con più incognite.

L'ordine segue le dipendenze: prima ciò che funziona con meno dati (la classifica), per ultimo ciò che
dipende da tutto il resto (i suggerimenti di mercato). Ogni fase finisce con qualcosa che si può mostrare
e con una verifica sul passato.

## Due traguardi

Si punta a entrambe le finestre di mercato, con ambizioni diverse.

| Traguardo | Quando | Cosa c'è | Cosa non c'è ancora |
|---|---|---|---|
| **Gennaio 2027**, versione ridotta | Apertura della finestra invernale, tra circa 7 settimane | Classifica simulata e interattiva (livello 1); rose 2026/27 caricate; fabbisogno per ruolo di ogni squadra; lista di candidati per somiglianza e costo, dichiarata sperimentale | Probabilità di buon acquisto, plausibilità imparata dai dati, effetto dell'acquisto sulla classifica |
| **Estate 2027**, versione completa | Pronta a giugno 2027 | Tutte le fasi da 1 a 5: proiezioni, valore, suggerimenti con probabilità calibrate, "e se" sul mercato (livello 2), app pubblica | Notizie e simulatore tra amici, che vengono dopo |

Il traguardo di gennaio è stretto: sono circa 40 ore di lavoro in tutto. Se il tempo non basta si taglia la
lista dei candidati, non la verifica della classifica.

## Fasi

| Fase | Contenuto | Durata | Finita quando |
|---|---|---|---|
| **0. Fondamenta** | Repo, CI, struttura dati, caricamento risultati, simulatore di base | 1-2 sett. | *Fatta.* Caricatori Transfermarkt, football-data (con le quote) e archivio Understat; rose 2026/27 verificate |
| **1. Classifica** | Forza da xG, peso alle partite recenti, Dixon-Coles, stima pre-stagionale dal valore della rosa | 2-3 sett. | *Prima parte fatta:* stagioni precedenti, peso alle partite recenti, neopromosse, xG provati; verifica su 2020–2025 contro i bookmaker in [STUDIO.md](STUDIO.md#verifica-sul-passato-backtest). Restano Dixon-Coles e la stima dalla rosa (che ha bisogno della fase 3) |
| **1b. Simulatore, livello 1** | App Streamlit: classifica simulata, cursori sulla forza delle squadre, risultati forzati | 1-2 sett. | *Costruito e provato in locale.* Manca la pubblicazione online, e la prova con i dati della stagione in corso |
| **G. Mercato di gennaio** | Fabbisogno per ruolo dalle rose a mano; candidati per somiglianza statistica, età e costo | 2-3 sett. | *Fatta:* pagina Mercato con fabbisogni e candidati per ogni club, verificata sulle finestre 2023–2025 ([STUDIO.md](STUDIO.md#versione-di-gennaio-2027-fase-g)). *Traguardo di gennaio* |
| **2. Anagrafica e proiezioni** | Collegamento degli ID tra le fonti; tabella giocatore-stagione; Marcel; modello dei minuti; coefficienti di campionato | 4-5 sett. | Almeno il 95% dei minuti di Serie A collegato tra Understat e Transfermarkt; errore inferiore a "uguale all'anno scorso" |
| **3. Valore** | Valore equo oggi e valore a 12 mesi | 2-3 sett. | Errore per fasce di valore, confrontato con "resta uguale, corretto per l'età" |
| **4. Mercato** | Plausibilità, probabilità di buon acquisto, incertezza per i campionati con pochi dati, lista per club | 5-6 sett. | Verifica su un'estate passata; curva di calibrazione pubblicata |
| **5. App completa e simulatore, livello 2** | Pagine giocatore, club e campionato; "e se" sul mercato; aggiornamento settimanale; pagina "come funziona" con le verifiche | 3-4 sett. | App online, dati che si aggiornano da soli. *Traguardo dell'estate* |
| **6. Notizie** | Raccolta dei feed, riconoscimento di giocatori e club, stadio della voce, affidabilità delle fonti | 3-4 sett. | 200 titoli etichettati a mano e accuratezza misurata |
| **7. Simulatore, livello 3** | Lega tra amici: API, login, mercato a turni, stagione simulata | Aperta | Una lega di prova giocata fino in fondo |

Dalla fase 1 alla 5 sono 20-26 settimane; da metà novembre a giugno ce ne sono circa 28. Il margine c'è, ma è poco.

## Simulatore interattivo

Tre livelli, ognuno utile da solo e costruito sul precedente.

| Livello | Cosa fa l'utente | Cosa serve | Quando |
|---|---|---|---|
| **1. "E se" sulla classifica** | Sceglie la data di partenza, alza o abbassa la forza di una squadra, fissa il risultato di una partita; le probabilità di scudetto, prime quattro e retrocessione si aggiornano | Solo il modello che c'è già, più l'app | **Fatto** (`app/streamlit_app.py`), da pubblicare |
| **2. "E se" sul mercato** | Aggiunge o toglie giocatori da una rosa; la forza della squadra si ricalcola dalle proiezioni e la classifica cambia | Fasi 1 e 2: il legame tra rosa e forza della squadra è il pezzo mancante | Primavera 2027 |
| **3. Lega tra amici** | Ognuno gestisce un club con un budget; mercato a turni; la stagione viene simulata giornata per giornata | Livello 2, più login, database e un'interfaccia vera (vedi [ARCHITETTURA.md](ARCHITETTURA.md#evoluzione)) | Dopo l'estate 2027 |

Dal punto di vista tecnico l'interattività non è un problema: 10.000 stagioni si simulano in circa un
secondo, quindi l'app può ricalcolare a ogni clic. La parte difficile è il livello 2, cioè tradurre
"questa rosa" in "questa forza in attacco e in difesa" in modo credibile.

Per il livello 3 restano da decidere le regole del gioco, che sono un lavoro di progettazione più che di
codice: budget iniziali, mercato libero o ad asta, quanto pesa il caso, cosa succede a stipendi e contratti.

## Rischi principali

| Rischio | Probabilità | Cosa si fa |
|---|---|---|
| Il traguardo di gennaio salta | Alta | Si pubblica quello che c'è (classifica interattiva) e il resto slitta alla versione estiva |
| Il dataset Transfermarkt resta fermo | Media | Rose a mano, già previste; per i campionati esteri resta il buco dei trasferimenti dell'estate 2026 |
| Understat cambia formato o chiude | Media | Copia locale di tutto lo scaricato. Per la classifica il rischio è già basso: il modello in uso non ha bisogno degli xG |
| Collegare gli ID richiede più del previsto | Alta | File di correzioni manuali; partire dalla sola Serie A e allargare dopo |
| I modelli non battono i riferimenti semplici | Media | È un risultato onesto e pubblicabile: si mostra il riferimento e si spiega perché |
| Il progetto si allarga troppo | Alta | Niente fase nuova finché la precedente non ha la sua verifica |

## Prossimi tre passi

1. **Pubblicare l'app** su Streamlit Community Cloud (classifica e mercato) e controllare che scarichi la stagione in corso.
2. **Aggiornare a fine gennaio 2027**: rose dopo il mercato invernale (`xmercato rose riconcilia`, procedura in [DATI.md](DATI.md#aggiornamento-automatico-da-una-lista-delle-rose-attuali)), poi `xmercato mercato suggerisci --finestra estate`.
3. **Fase 2, anagrafica e proiezioni**: è la base della probabilità di buon acquisto, che oggi manca ai candidati.
