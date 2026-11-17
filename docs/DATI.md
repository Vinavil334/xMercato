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

## Rose raccolte a mano

Un file CSV per stagione, versionato nella repo: [`rose/serie_a_2026_27.csv`](../rose/serie_a_2026_27.csv),
una riga per giocatore in rosa. Va aggiornato alla chiusura di ogni finestra di mercato.

### Formato

| Colonna | Esempio (inventato) | Note |
|---|---|---|
| `club` | `Inter` | Stesso nome usato nei file dei risultati |
| `giocatore` | `Mario Rossi` | |
| `tm_id` | `123456` | ID Transfermarkt, dall'indirizzo della pagina del giocatore. È la chiave che collega allo storico: senza, il giocatore non ha passato. Obbligatorio |
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

### Da dove si parte

La bozza è stata generata dallo snapshot Transfermarkt di luglio 2026 con il workflow
[Bozza delle rose](../.github/workflows/rose-bozza.yml): 638 giocatori, tutte le righe con `verificato = no`.
Cosa contiene e cosa no:

- **17 squadre su 20 quasi complete, ma a inizio luglio.** Mancano i movimenti dell'estate 2026 e ci
  sono tutti i rientri dai prestiti: per questo le rose hanno 31-40 giocatori.
- **Neopromosse quasi vuote.** La Serie B non è coperta dal dataset: Frosinone e Monza hanno un
  giocatore, il Venezia quattro. Vanno compilate da zero.
- **`tipo` sempre vuoto.** Il dataset non distingue i prestiti.
- **Campi mancanti:** 145 date di arrivo (soprattutto giovani del vivaio), 91 scadenze, 114 valori.

### Come si aggiorna

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
