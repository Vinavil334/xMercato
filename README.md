# xMercato

Player projections, transfer suggestions and league table simulation for Serie A, built on free data.

xMercato aims to answer three linked questions:

1. **How will a player perform, and what will he be worth, next season?**
2. **Which realistic signings should each of the 20 Serie A clubs make, and how likely is each to work out?**
3. **How will the league table end up?**

The pieces feed each other: projected players change a squad's strength, and squad strength drives the
simulated table, so a suggested signing can be scored by the points it is expected to add.

> **Status: early.** The league table simulator works. Everything else is designed but not built.
> See the [roadmap](docs/ROADMAP.md).

## Try it

```bash
git clone https://github.com/Vinavil334/xMercato.git
cd xMercato
uv sync --extra dev

# Where did the 2025/26 season look like it was heading on 6 January 2026?
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

For the current season, point `--results` at the football-data.co.uk file, for example
`https://www.football-data.co.uk/mmz4281/2627/I1.csv`.

The model behind it is a deliberately simple baseline: team attack and defence strengths fitted on
results with a penalised Poisson model, then a Monte Carlo simulation of the remaining fixtures.
Table ties are broken by goal difference, not by Serie A's head-to-head rules.

## Documentation

The design documents are in Italian.

| Document | Content |
|---|---|
| [docs/STUDIO.md](docs/STUDIO.md) | The four models, how each is validated, strengths, limits, open questions |
| [docs/DATI.md](docs/DATI.md) | Data sources, what each covers, current status, legal notes |
| [docs/ARCHITETTURA.md](docs/ARCHITETTURA.md) | Pipeline, languages, free services, how it could grow |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Phases, effort, exit criteria, risks |

## Development

```bash
make check   # ruff + pytest
```

## Data and licence

Code is released under the [MIT licence](LICENSE). No third-party data is stored in this repository,
except one small public-domain results file used by the tests
(from [datasets/football-datasets](https://github.com/datasets/football-datasets), sourced from football-data.co.uk).
Each data source keeps its own terms: see [docs/DATI.md](docs/DATI.md).

This is a personal, non-commercial project. Its outputs are estimates, not betting or financial advice.
