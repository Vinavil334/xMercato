# xMercato

Proiezioni dei giocatori, suggerimenti di mercato e simulazione della classifica per la Serie A, costruiti su dati gratuiti.

xMercato vuole rispondere a tre domande collegate:

1. **Come renderà un giocatore, e quanto varrà, la prossima stagione?**
2. **Quali acquisti verosimili dovrebbe fare ciascuna delle 20 squadre di Serie A, e con che probabilità funzioneranno?**
3. **Come finirà il campionato?**

I tre pezzi si alimentano a vicenda: le proiezioni dei giocatori cambiano la forza di una rosa, e la forza
della rosa guida la classifica simulata. Così ogni acquisto suggerito si può valutare in punti attesi.

> **Stato: agli inizi.** Il simulatore interattivo della classifica funziona. Il resto è progettato ma non
> ancora costruito. Vedi la [roadmap](docs/ROADMAP.md).

## Il simulatore

```bash
git clone https://github.com/Vinavil334/xMercato.git
cd xMercato
uv sync --extra dev
uv run streamlit run app/streamlit_app.py
```

Nell'app si può:

- scegliere fino a che data usare i risultati, per rivedere il campionato com'era in quel momento;
- rendere una squadra più o meno forte (gol fatti e gol subiti) e vedere come cambiano punti attesi e
  probabilità di scudetto, prime quattro e retrocessione;
- fissare il risultato di una partita ancora da giocare.

Scenario e simulazione di base usano gli stessi numeri casuali: cambiano solo le partite toccate dalle
modifiche, quindi le differenze mostrate non sono rumore.

L'app scarica la stagione in corso da football-data.co.uk; se non ci riesce usa la stagione 2025/26
inclusa nella repo.

## Da riga di comando

```bash
# Dove sembrava andare la stagione 2025/26 al 6 gennaio 2026?
uv run xmercato simulate --results src/xmercato/samples/serie_a_2025_26.csv --as-of 2026-01-06 --seed 42
```

```
Modello: solo stagione, gol
179 matches played, 201 simulated x 10000 seasons

            played  points  exp_points  p_title  p_top4  p_relegation
team
Inter           17      39      84.600    0.717   0.995         0.000
Napoli          17      37      77.900    0.136   0.906         0.000
Milan           17      38      77.700    0.129   0.901         0.000
...
Verona          17      12      28.600    0.000   0.000         0.794
Pisa            19      12      28.400    0.000   0.000         0.797
```

Per la stagione in corso basta passare a `--results` il file di football-data.co.uk, per esempio
`https://www.football-data.co.uk/mmz4281/2627/I1.csv`.

Il modello è volutamente semplice: forza in attacco e in difesa di ogni squadra stimata dai risultati con
un modello di Poisson penalizzato, poi simulazione Monte Carlo delle partite rimanenti. A parità di punti
decide la differenza reti, non gli scontri diretti come nel regolamento della Serie A.

Con lo storico (`xmercato storico`, vedi [docs/DATI.md](docs/DATI.md#storico-per-la-classifica)) il
modello usa anche le due stagioni precedenti, come fa l'app:

```bash
uv run xmercato simulate --storico data/storico/serie_a.csv --modello gol
# Quanto avrebbero previsto bene i modelli sulle stagioni 2020-2025, contro le quote dei bookmaker
uv run xmercato backtest --da 2020 --a 2025
```

Risultati del backtest in [docs/STUDIO.md](docs/STUDIO.md#verifica-sul-passato-backtest): con le
stagioni precedenti il modello recupera più di metà della distanza dai bookmaker.

## Le rose

Le rose 2026/27 delle 20 squadre sono in [`rose/serie_a_2026_27.csv`](rose/serie_a_2026_27.csv): 588
giocatori, verificati incrociando l'ultimo snapshot Transfermarkt, le voci Wikipedia dei club e il
riepilogo dei trasferimenti di Tuttomercatoweb. Per controllare il file:

```bash
uv run xmercato rose controlla rose/serie_a_2026_27.csv
```

Formato e procedura di aggiornamento sono in [docs/DATI.md](docs/DATI.md#rose-raccolte-a-mano).

## Documentazione

| Documento | Contenuto |
|---|---|
| [docs/STUDIO.md](docs/STUDIO.md) | I quattro modelli, come si valida ciascuno, pro, limiti, decisioni prese |
| [docs/DATI.md](docs/DATI.md) | Fonti dati, cosa coprono, stato attuale, note legali |
| [docs/ARCHITETTURA.md](docs/ARCHITETTURA.md) | Pipeline, linguaggi, servizi gratuiti, evoluzione |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Fasi, tempi, criteri di completamento, rischi |

## Sviluppo

```bash
make check   # ruff + pytest
make app     # avvia il simulatore in locale
```

## Dati e licenza

Il codice è rilasciato con [licenza MIT](LICENSE). Di dati di terze parti, la repo contiene solo:

- un file di risultati di pubblico dominio, usato dai test e come riserva dall'app
  (da [datasets/football-datasets](https://github.com/datasets/football-datasets), fonte football-data.co.uk);
- le rose in `rose/`, partite dal dataset [transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets)
  (fonte Transfermarkt) e aggiornate con le fonti elencate in `rose/fonti/`.
Ogni fonte mantiene le proprie condizioni d'uso: vedi [docs/DATI.md](docs/DATI.md).

È un progetto personale e non commerciale. I risultati sono stime, non consigli per scommesse o investimenti.
