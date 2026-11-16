# xMercato

Proiezioni dei giocatori, suggerimenti di mercato e simulazione della classifica per la Serie A, costruiti su dati gratuiti.

xMercato vuole rispondere a tre domande collegate:

1. **Come renderà un giocatore, e quanto varrà, la prossima stagione?**
2. **Quali acquisti verosimili dovrebbe fare ciascuna delle 20 squadre di Serie A, e con che probabilità funzioneranno?**
3. **Come finirà il campionato?**

I tre pezzi si alimentano a vicenda: le proiezioni dei giocatori cambiano la forza di una rosa, e la forza
della rosa guida la classifica simulata. Così ogni acquisto suggerito si può valutare in punti attesi.

> **Stato: agli inizi.** Il simulatore della classifica funziona. Il resto è progettato ma non ancora costruito.
> Vedi la [roadmap](docs/ROADMAP.md).

## Provalo

```bash
git clone https://github.com/Vinavil334/xMercato.git
cd xMercato
uv sync --extra dev

# Dove sembrava andare la stagione 2025/26 al 6 gennaio 2026?
uv run xmercato simulate --results tests/data/serie_a_2025_26.csv --as-of 2026-01-06 --seed 42
```

```
179 matches played, 201 simulated x 10000 seasons

            played  points  exp_points  p_title  p_top4  p_relegation
team
Inter           17      39      84.700    0.719   0.994         0.000
Milan           17      38      77.800    0.133   0.900         0.000
Napoli          17      37      77.700    0.130   0.901         0.000
...
Verona          17      12      28.600    0.000   0.000         0.793
Pisa            19      12      28.400    0.000   0.000         0.794
```

Per la stagione in corso basta passare a `--results` il file di football-data.co.uk, per esempio
`https://www.football-data.co.uk/mmz4281/2627/I1.csv`.

Il modello è volutamente semplice: forza in attacco e in difesa di ogni squadra stimata dai risultati con
un modello di Poisson penalizzato, poi simulazione Monte Carlo delle partite rimanenti. A parità di punti
decide la differenza reti, non gli scontri diretti come nel regolamento della Serie A.

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
```

## Dati e licenza

Il codice è rilasciato con [licenza MIT](LICENSE). La repo non contiene dati di terze parti, a parte un
piccolo file di risultati di pubblico dominio usato dai test
(da [datasets/football-datasets](https://github.com/datasets/football-datasets), fonte football-data.co.uk).
Ogni fonte mantiene le proprie condizioni d'uso: vedi [docs/DATI.md](docs/DATI.md).

È un progetto personale e non commerciale. I risultati sono stime, non consigli per scommesse o investimenti.
