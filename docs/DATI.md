# Fonti dati

Stato verificato il **16 novembre 2026**. Le fonti gratuite di dati calcistici cambiano spesso
(nel 2026 sono cambiate due delle più importanti), quindi questa pagina va ricontrollata a ogni fase.

## In sintesi

- **Non esiste più una fonte gratuita, dettagliata e aggiornata** come era FBref fino a gennaio 2026.
  Il livello di dettaglio che si può tenere aggiornato gratis è quello di **Understat**: tiri, xG, xA,
  passaggi chiave, xGChain/xGBuildup, per i cinque campionati principali.
- Statistiche più ricche (passaggi progressivi, azioni difensive, possesso) esistono solo come
  **archivi congelati** di FBref: utili per ricerca e per allenare modelli sul passato, non come
  feature di un modello che deve girare ogni settimana.
- Per valori di mercato e trasferimenti la fonte è **Transfermarkt**, tramite dataset pubblici.
  Il principale ha gli **aggiornamenti in pausa da luglio 2026**: lo storico c'è tutto, le rose 2026/27 no.

## Fonti principali

| Fonte | Cosa contiene | Copertura | Accesso | Stato e rischi |
|---|---|---|---|---|
| [Understat](https://understat.com) | Per giocatore e partita: xG, npxG, xA, tiri (con coordinate), passaggi chiave, xGChain, xGBuildup. Per squadra: xG, xGA, PPDA, xPTS | Serie A, Premier, Liga, Bundesliga, Ligue 1, RFPL dal 2014/15 | Scraping (dati JSON nelle pagine). Librerie: `soccerdata`, `understatapi` | Attiva. Nessuna API né licenza ufficiale: gli scraper possono rompersi |
| [dcaribou/transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets) | 12 tabelle: 50.000+ giocatori, 1,89 M presenze (minuti, gol, assist, cartellini), 650.000+ valutazioni storiche, 175.000+ trasferimenti, formazioni, eventi | 65 competizioni | File CSV e DuckDB scaricabili; anche su Kaggle | **Aggiornamenti in pausa: dati fino al 6 luglio 2026**, valutazioni fino al 12 giugno 2026, rose 2026/27 assenti. Repo con licenza CC0 |
| [salimt/football-datasets](https://github.com/salimt/football-datasets) | Datalake Transfermarkt: 93.000+ giocatori, **143.000 infortuni**, storico trasferimenti, compagni di squadra | Ampia | CSV su GitHub e Kaggle | Ultimo aggiornamento dichiarato: ottobre 2025 |
| [football-data.co.uk](https://www.football-data.co.uk/italym.php) | Risultati, tiri, corner, cartellini e **quote dei bookmaker** per partita | Serie A dal 1993/94 | CSV diretto (`.../mmz4281/2526/I1.csv`) | Attiva. Copia di pubblico dominio su [datasets/football-datasets](https://github.com/datasets/football-datasets) (lì il file 2026/27 non c'era ancora al momento della verifica) |
| [worldfootballR_data](https://github.com/JaseZiv/worldfootballR_data) | Archivio FBref Big 5 per giocatore-stagione; **mappa FBref ↔ Transfermarkt** (15.440 giocatori); tiri Understat | Stagioni complete 2009/10–2021/22, xG dal 2017/18 (verificato sulla tabella "standard": 38.008 righe) | File `.rds` e CSV su GitHub (in Python: `pyreadr`) | **Archiviato**, non più mantenuto. Solo storico |
| Snapshot FBref su Kaggle | Statistiche avanzate Big 5 per le stagioni 2023/24 e successive, fino a gennaio 2026 | Varia per autore | Kaggle | Congelati. Licenza e qualità da controllare caso per caso |
| [ClubElo](http://clubelo.com) | Rating Elo storici dei club europei | Europa | API CSV | Non verificata in questa sessione |

## Fonti secondarie

| Fonte | A cosa servirebbe | Perché non è nel nucleo |
|---|---|---|
| [StatsBomb Open Data](https://github.com/statsbomb/open-data) | Dati evento completi (ogni passaggio, pressione, tiro) | Per la Serie A c'è solo il 2015/16 (più il 1986/87). Ottima per esperimenti, inutilizzabile per stagioni recenti |
| [API-Football](https://www.api-football.com) | Statistiche per campionati fuori dai Big 5 | Piano gratuito: 100 richieste al giorno, 10 al minuto, solo stagioni recenti. Basta per prove, non per uno storico |
| FotMob, Sofascore | xG e statistiche partita per moltissimi campionati | Nessuna API pubblica ufficiale; i termini d'uso limitano lo scraping (worldfootballR ha tolto il supporto a FotMob per questo). Da valutare più avanti, con cautela |
| [Capology](https://www.capology.com/it/serie-a/stipendi/) | Stipendi e durata dei contratti | Sono stime; l'accesso completo costa 4.000 USD l'anno e l'API è solo enterprise |
| EA Sports FC / SoFIFA | Attributi omogenei per quasi tutti i professionisti | Sono valutazioni di un videogioco: utili solo come informazione di partenza per chi non ha statistiche avanzate |

## Cosa manca, e come ci si convive

1. **Rose e valori 2026/27.** Finché il dataset Transfermarkt non riparte, le rose delle 20 squadre di
   Serie A si aggiornano a mano partendo da una bozza: vedi [qui sotto](#rose-raccolte-a-mano).
2. **Giocatori fuori dai Big 5.** Per Eredivisie, Portogallo, Belgio, Sud America, Serie B ci sono solo
   minuti, gol e assist (da Transfermarkt). È il limite più pesante per i suggerimenti di mercato,
   perché la Serie A compra molto da quei campionati.
3. **Stipendi, commissioni, clausole.** Non osservabili gratis. Il "verosimile" si basa su costo del
   cartellino stimato e abitudini di spesa del club.
4. **Difensori e portieri.** Le statistiche pubbliche misurano bene chi tira e chi rifinisce, male gli altri.

## Storico per la classifica

`uv run xmercato storico --a 2026 --tiri serie_a_shot_data.rds` costruisce `data/storico/serie_a.csv`:
una riga per partita di Serie A dal 2014/15, con risultato, xG delle due squadre e quote di chiusura.
Su GitHub lo stesso comando gira nel workflow **Dati storici** (avvio a mano dalla scheda Actions), che
pubblica la tabella come artefatto.

| Pezzo | Fonte | Copertura |
|---|---|---|
| Risultati e quote 1X2 | football-data.co.uk. Quote di chiusura Pinnacle (`PSC*`) quando ci sono, altrimenti la media di chiusura del mercato (`AvgC*`) | Tutte le stagioni, compresa quella in corso |
| xG per partita | Somma degli xG dei tiri nell'archivio Understat di [worldfootballR_data](https://github.com/JaseZiv/worldfootballR_data) (`understat_shots/serie_a_shot_data.rds`, letto con il pacchetto `rdata`: `uv sync --extra storico`) | Complete dal 2014/15 al 2023/24; 181 partite su 380 nel 2024/25; niente dopo |

I nomi delle squadre delle due fonti vengono allineati (`src/xmercato/ingest/teams.py`); le partite si
abbinano per squadre e stagione, e una data diversa di più di tre giorni (per esempio una partita
sospesa e ripresa) produce un avviso.

**Il buco: xG della stagione in corso.** L'archivio è fermo e il sito di Understat non è stato toccato
dal progetto. Per la classifica non è un problema, perché il backtest mostra che gli xG migliorano le
previsioni di poco (vedi [STUDIO.md](STUDIO.md#verifica-sul-passato-backtest)) e il modello in uso
lavora sui soli gol. Torneranno necessari per le proiezioni dei giocatori (fase 2): allora andrà scelta
una fonte aggiornata, valutandone i termini d'uso.

## Tabelle per il mercato

`uv run xmercato mercato dati` legge le tabelle delle partite del dataset Transfermarkt (presenze,
formazioni, partite, valori, trasferimenti) e scrive in `data/mercato/`:

| File | Contenuto |
|---|---|
| `giocatori_stagioni.csv.gz` | Una riga per giocatore, stagione e club, dal 2018/19: convocazioni (panchina compresa), presenze, partite da titolare, minuti, gol, assist, cartellini, posizione in cui partiva più spesso, valore a inizio stagione, al 1° gennaio e a fine stagione. Le stesse cifre per il solo girone d'andata |
| `giocatori.csv.gz` | Anagrafica: nascita, cittadinanza, posizione, contratto, club e valore a luglio 2026 |
| `trasferimenti_serie_a.csv.gz` | Trasferimenti da e verso club italiani dal 2018 |
| `club.csv.gz`, `campionati.csv.gz` | Club e campionati del dataset |

Copertura delle statistiche: 14 campionati (Serie A, Premier League, Liga, Bundesliga, Ligue 1,
Portogallo, Olanda, Belgio, Turchia, Russia, Scozia, Grecia, Ucraina, Danimarca), stagioni 2018/19–2025/26.
Mancano Serie B e Sudamerica. Le tabelle originali pesano qualche centinaio di MB e si scaricano solo
da GitHub: il workflow **Dati mercato** (avvio a mano dalla scheda Actions) costruisce le tabelle, le
pubblica come artefatto e mette nel riepilogo la verifica dei modelli.

`uv run xmercato mercato suggerisci` usa queste tabelle e le rose verificate per scrivere
`mercato/fabbisogni_<finestra>_<anno>.csv` e `mercato/candidati_<finestra>_<anno>.csv`, che l'app legge.
Questi due file sono nel repository: sono piccoli e derivati da un dataset CC0.

## Rose raccolte a mano

Un file CSV per stagione, versionato nella repo: [`rose/serie_a_2026_27.csv`](../rose/serie_a_2026_27.csv),
una riga per giocatore in rosa. Va aggiornato alla chiusura di ogni finestra di mercato.

### Formato

| Colonna | Esempio (inventato) | Note |
|---|---|---|
| `club` | `Inter` | Stesso nome usato nei file dei risultati |
| `giocatore` | `Mario Rossi` | |
| `tm_id` | `123456` | ID Transfermarkt, dall'indirizzo della pagina del giocatore. È la chiave che collega allo storico. Si può lasciare vuoto per chi non ha storico nel dataset (per esempio chi arriva dalla Serie B o da campionati non coperti): il controllo lo segnala come avviso |
| `data_nascita` | `2001-03-15` | Serve anche a risolvere gli omonimi |
| `ruolo` | `ATT` | `POR`, `DIF`, `CEN`, `ATT`; il ruolo dettagliato arriva dallo storico |
| `arrivo` | `2026-08-20` | Data di arrivo nel club |
| `tipo` | `definitivo` | `definitivo`, `prestito`, `prestito_diritto`, `prestito_obbligo`, `vivaio`. Vuoto finché non verificato |
| `scadenza` | `2030-06-30` | Scadenza del contratto, se nota |
| `valore_mln` | `12.5` | Valore di mercato in milioni, col punto decimale |
| `valore_data` | `2026-09-01` | Data a cui si riferisce il valore |
| `fonte` | `manuale` | `tm_2026_07` per le righe della bozza, `manuale` per quelle aggiunte o riscritte a mano |
| `verificato` | `si` | `si` quando la riga è stata controllata sulla rosa attuale, altrimenti `no` |

Date sempre nel formato `AAAA-MM-GG`. Il file si apre con qualsiasi foglio di calcolo, ma va salvato come
CSV con la virgola come separatore e codifica UTF-8.

### Stato attuale (17 novembre 2026)

Le rose delle 20 squadre sono **verificate**: 588 giocatori, tutti con `verificato = si`.
Il file è stato costruito in tre passaggi.

1. **Bozza.** Dallo snapshot Transfermarkt di luglio 2026, con il workflow
   [Bozza delle rose](../.github/workflows/rose-bozza.yml): 638 giocatori, situazione di inizio luglio.
2. **Rose attuali.** Trascritte dalle voci Wikipedia dei club, aggiornate tra il 28 agosto e il 13
   ottobre; per il Genoa, la cui voce era ferma a febbraio, dal listone di fantacalcio-online.
   Elenco e date in [`rose/fonti/wikipedia_2026_27.csv`](../rose/fonti/wikipedia_2026_27.csv).
3. **Controllo incrociato.** Con il riepilogo dei trasferimenti ufficiali di Tuttomercatoweb
   ([`rose/fonti/tmw_trasferimenti_estate_2026.csv`](../rose/fonti/tmw_trasferimenti_estate_2026.csv),
   808 operazioni). Ha corretto le pagine Wikipedia aggiornate prima della chiusura del mercato: 14
   giocatori ceduti tolti e 11 acquisti dell'ultimo giorno aggiunti. Ha anche permesso di ricavare la
   formula dei prestiti. L'elenco delle correzioni è in testa al file delle fonti.

Ogni decisione della riconciliazione (confermato, aggiunto, rimosso, escluso) è in
[`rose/fonti/decisioni_riconciliazione_2026_27.csv`](../rose/fonti/decisioni_riconciliazione_2026_27.csv).

Cosa resta incompleto:

- **27 giocatori senza `tm_id`**, quasi tutti arrivati da campionati non coperti dal dataset (Serie B,
  giovanili, campionati minori): sono in rosa ma senza storico collegato.
- **Formula dei prestiti precisa solo in parte.** Su 86 prestiti, 6 sono con obbligo e 4 con diritto
  di riscatto, verificati su comunicati o articoli. Gli altri sono registrati come `prestito`
  generico: possono avere un diritto di riscatto che le fonti usate non riportano.
- **13 giocatori senza `tipo`**: giovani o arrivi minori per cui nessuna fonte indica la formula.
- **Date di arrivo e scadenze dei nuovi contratti** non sono state raccolte: la scadenza del dataset
  è quella del vecchio club, quindi per i nuovi arrivi è vuota.
- **Valori di mercato** fermi a giugno 2026 (ultimo aggiornamento del dataset), più vecchi per chi
  arriva da campionati non coperti: la data è in `valore_data`.
- **Giovani aggregati.** Chi è nella prima squadra secondo le fonti è nel file; i giovani acquistati
  per Primavera e Under 23 no.

### Aggiornamento automatico da una lista delle rose attuali

Il modo più rapido è partire da un elenco delle rose attuali, solo nomi, e lasciare che il comando
`riconcilia` faccia il resto. L'elenco è in [`rose/fonti/wikipedia_2026_27.csv`](../rose/fonti/wikipedia_2026_27.csv),
con in testa la pagina e la data di ogni rosa e le correzioni fatte con la seconda fonte.

```bash
uv run xmercato rose riconcilia --lista rose/fonti/wikipedia_2026_27.csv --tm <cartella tabelle> --report decisioni.csv
```

Per ogni squadra presente nell'elenco:

- chi è già nel file viene **confermato** (`verificato = si`) e mantiene i dati della bozza;
- chi manca viene **aggiunto**, cercandolo per nome tra tutti i giocatori del dataset Transfermarkt
  (ID, data di nascita, ruolo, valore). La scadenza resta vuota, perché quella del dataset è del vecchio contratto;
- chi non è nell'elenco viene **rimosso**; se un giocatore compare in un'altra squadra non ancora
  verificata, viene tolto da lì;
- i nomi con più omonimi plausibili non vengono indovinati: il comando li elenca e basta scrivere il
  `tm_id` giusto nella colonna `tm_id` dell'elenco;
- un giocatore di prima squadra che non è nel dataset viene aggiunto senza `tm_id`; un giovane della
  seconda tabella che non è nel dataset viene escluso.

Il `tipo` viene dalla nota dell'elenco: `prestito_obbligo` se cita un obbligo di riscatto,
`prestito_diritto` se cita un diritto (o un'opzione), `prestito` per gli altri prestiti, `definitivo`
per acquisti e svincolati. Senza nota: `vivaio` per chi ha al massimo 23 anni e nessun trasferimento in
entrata registrato, altrimenti `definitivo`. Le correzioni fatte a mano nel file restano anche se il
comando viene rilanciato.

Conviene sempre controllare l'elenco con una seconda fonte: una pagina aggiornata anche solo due
giorni prima della chiusura del mercato non contiene le operazioni dell'ultimo giorno.

Le squadre che non compaiono nell'elenco restano com'erano. La cartella delle tabelle è quella
scaricata dal workflow della bozza; i file servono solo in locale e non vanno nella repo.

### Come si aggiorna a mano

1. Per una squadra alla volta, apri la sua rosa attuale su Transfermarkt e confrontala con le righe del file.
2. **Giocatore ancora in rosa:** controlla ruolo, scadenza e valore, compila `tipo`, metti `verificato = si`.
3. **Giocatore partito** (ceduto, in prestito altrove, svincolato): cancella la riga.
4. **Nuovo arrivo:** aggiungi una riga con `fonte = manuale` e `verificato = si`. Il `tm_id` è il numero
   alla fine dell'indirizzo della sua pagina Transfermarkt.
5. Controlla il file:

   ```bash
   uv run xmercato rose controlla rose/serie_a_2026_27.csv
   ```

   Il comando mostra una tabella per club (giocatori, verificati, valore) e due tipi di segnalazioni:
   **errori**, che rendono il file inutilizzabile e indicano le righe da correggere, e **avvisi**, che
   segnalano cose incomplete o sospette, come rose troppo grandi o contratti già scaduti.

Si può fare anche una squadra alla volta: il file è utilizzabile in ogni momento, purché senza errori.

Per rigenerare la bozza da zero (per esempio se il dataset Transfermarkt riparte), il workflow si lancia a
mano dalla scheda *Actions* di GitHub. Se il file esiste già, si ferma, a meno di scegliere esplicitamente
di sovrascriverlo: così le correzioni fatte a mano non si perdono per errore.

## Identità dei giocatori

Ogni fonte ha i propri ID. Collegarle è un lavoro a sé (fase 2 della roadmap):

- FBref ↔ Transfermarkt: mappa già pronta in `worldfootballR_data` (ferma, da estendere).
- Understat ↔ Transfermarkt: da costruire con nome normalizzato, data di nascita, squadra e stagione;
  i casi ambigui vanno in un file di correzioni manuali versionato nella repo.

## Note legali

- Transfermarkt considera i propri dati protetti e i termini d'uso vietano lo scraping; i dataset
  pubblici esistono comunque e sono molto usati. Understat non pubblica una licenza.
- Regole del progetto: **nella repo niente dati grezzi**, con due eccezioni piccole e dichiarate: una
  stagione di risultati di pubblico dominio (per test ed esempi) e le rose in `rose/`, partite dal
  dataset Transfermarkt pubblico, che ha licenza CC0, e corrette a mano. Scraping lento, con cache, solo
  per ciò che serve; uso personale e non commerciale; fonti sempre citate nell'app.
- Se il progetto dovesse diventare pubblico "sul serio" o commerciale, le fonti vanno ripensate.

## Dove finiscono i dati

```
data/                 # ignorata da git
├── raw/<fonte>/      # file scaricati, così come sono
├── staging/          # una tabella pulita per fonte (Parquet)
├── marts/            # tabelle per i modelli: giocatore-stagione, club-stagione, partite
└── outputs/          # previsioni pubblicabili, lette dall'app
```
