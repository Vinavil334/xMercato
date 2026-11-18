"""Command line entry point.

xmercato simulate --results ...      league table simulation (or --storico, with past seasons)
xmercato rose bozza --out ...        squad draft from the Transfermarkt snapshot
xmercato rose controlla FILE         check a hand-maintained squad file
xmercato rose riconcilia --lista ... apply a list of current squads to the squad file
xmercato storico --da 2014 --a 2026  results, odds and xG for several seasons
xmercato backtest --da 2020 --a 2025 how the models would have done, against the bookmakers
xmercato mercato dati --out DIR      player-season table from the Transfermarkt match data
xmercato mercato suggerisci          needs and candidates of every club for a window
xmercato mercato verifica            backtest of needs and candidates on past windows
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from xmercato import rose, rose_sync
from xmercato.evaluation import backtest, candidates_backtest, needs_backtest
from xmercato.features import player_seasons
from xmercato.ingest import football_data, history, transfermarkt, understat
from xmercato.models import forecast
from xmercato.recommend import data as market_data
from xmercato.recommend import market
from xmercato.sim import season


def _simulate(args: argparse.Namespace) -> None:
    if args.storico:
        past = history.read(args.storico)
        current = args.stagione if args.stagione is not None else int(past["season"].max())
        results = past[past["season"] == current]
    elif args.results:
        results = football_data.load_results(args.results)
        current = 0
        past = results.assign(season=current)
    else:
        sys.exit("Serve --results (una stagione) oppure --storico (più stagioni).")
    config = forecast.CONFIGS[args.modello]
    if args.shrinkage is not None:
        config = config.with_(shrinkage=args.shrinkage)

    teams = sorted(set(results["home"]) | set(results["away"]))
    as_of = pd.Timestamp(args.as_of) if args.as_of else results["date"].max()
    results = results[results["date"] <= as_of][
        ["date", "home", "away", "home_goals", "away_goals"]
    ]
    strengths = forecast.fit_as_of(past, current, as_of + pd.Timedelta(days=1), config, teams)
    table = season.simulate(strengths, results, n_sims=args.n_sims, seed=args.seed)
    summary = season.summarise(table)

    todo = len(season.remaining_fixtures(results, teams))
    print(f"Modello: {config.name}")
    print(f"{len(results)} matches played, {todo} simulated x {args.n_sims} seasons\n")
    with pd.option_context("display.width", 120, "display.float_format", "{:.3f}".format):
        print(summary.to_string())


def _rose_bozza(args: argparse.Namespace) -> None:
    tm = transfermarkt.load_all(args.tm)
    squads, mapping = rose.draft(tm, season=args.stagione)

    print("Club trovati nel dataset Transfermarkt:")
    print(mapping.to_string(index=False), end="\n\n")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    squads.to_csv(out, index=False, encoding="utf-8")
    print(f"Bozza scritta in {out}: {len(squads)} giocatori\n")
    print(rose.summary(squads, args.stagione).to_string())


def _rose_controlla(args: argparse.Namespace) -> None:
    squads = rose.read(args.file)
    problems = rose.check(squads, season=args.stagione)
    print(rose.summary(squads, args.stagione).to_string(), end="\n\n")
    for problem in problems:
        print(problem)
    if rose.is_valid(problems):
        print("\nFile utilizzabile." + (" Ci sono avvisi da guardare." if problems else ""))
    else:
        print("\nIl file ha errori da correggere.")
        sys.exit(1)


def _rose_riconcilia(args: argparse.Namespace) -> None:
    squads = rose.read(args.file)
    current = rose_sync.read_list(args.lista)
    players = transfermarkt.load_table("players", args.tm)
    valuations = transfermarkt.load_table("player_valuations", args.tm)
    outcome = rose_sync.reconcile(squads, current, players, valuations, season=args.stagione)

    counts = outcome.report.groupby(["club", "esito"]).size().unstack(fill_value=0)
    with pd.option_context("display.width", 160):
        print(counts.to_string(), end="\n\n")
    if args.report:
        outcome.report.to_csv(args.report, index=False, encoding="utf-8")
        print(f"Dettaglio delle decisioni in {args.report}")
    if len(outcome.unresolved):
        print("Omonimi da risolvere (aggiungi il tm_id giusto nella lista e rilancia):")
        print(outcome.unresolved.to_string(index=False), end="\n\n")
    outcome.squads.to_csv(args.file, index=False, encoding="utf-8")
    print(f"{args.file} aggiornato: {len(outcome.squads)} giocatori")


def _storico(args: argparse.Namespace) -> None:
    seasons = list(range(args.da, args.a + 1))
    shots = understat.read_shots(args.tiri) if args.tiri else None
    xg = understat.match_xg(shots) if shots is not None else None
    table = history.build(seasons, xg=xg)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out, index=False)
    summary = table.groupby("season").agg(
        partite=("home", "size"),
        con_xg=("home_xg", "count"),
        con_quote=("odds_home", "count"),
        fonte_quote=("odds_source", lambda s: ",".join(sorted(set(s) - {""}))),
    )
    print(summary.to_string(), end="\n\n")
    print(f"{len(table)} partite scritte in {out}")


def _backtest(args: argparse.Namespace) -> None:
    past = history.read(args.storico)
    seasons = range(args.da, args.a + 1)
    configs = [forecast.CONFIGS[name] for name in args.modelli]
    scored, tables = backtest.run(past, seasons, configs, n_sims=args.n_sims)
    with pd.option_context("display.width", 160):
        print("Partita per partita (più basso è meglio):")
        print(backtest.summary(scored).sort_values("log_loss").to_string(), end="\n\n")
        print("Log loss per stagione:")
        by_season = backtest.summary(scored, ["season", "model"])["log_loss"].unstack()
        print(by_season.to_string(), end="\n\n")
        print("Errore medio sui punti finali, simulando dalla giornata indicata:")
        mae = tables.pivot_table(index="model", columns="round", values="mae").round(2)
        print(mae.to_string())
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        scored.to_csv(out / "partite.csv", index=False)
        tables.to_csv(out / "classifiche.csv", index=False)
        print(f"\nDettagli in {out}/")


def _mercato_dati(args: argparse.Namespace) -> None:
    def load(table: str) -> pd.DataFrame:
        print(f"Leggo {table}…", flush=True)
        return transfermarkt.load_table(table, args.tm)

    competitions = load("competitions")
    clubs = load("clubs")
    table = player_seasons.build(
        load("appearances"),
        load("game_lineups"),
        load("games"),
        competitions,
        load("player_valuations"),
        first_season=args.da,
    )
    players = load("players")
    transfers = load("transfers")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    table.to_csv(out / "giocatori_stagioni.csv.gz", index=False)
    keep = set(table["player_id"]) | set(transfers["player_id"])
    players = players[players["player_id"].isin(keep)]
    players.drop(
        columns=["image_url", "url", "player_code", "city_of_birth"], errors="ignore"
    ).to_csv(out / "giocatori.csv.gz", index=False)
    italian = set(clubs.loc[clubs["domestic_competition_id"] == "IT1", "club_id"])
    italian |= set(table.loc[table["competition_id"] == "IT1", "club_id"])
    date = pd.to_datetime(transfers["transfer_date"], errors="coerce")
    moves = transfers[
        (date >= f"{args.da}-01-01")
        & (transfers["to_club_id"].isin(italian) | transfers["from_club_id"].isin(italian))
    ]
    moves.to_csv(out / "trasferimenti_serie_a.csv.gz", index=False)
    clubs.drop(columns=["filename", "url"], errors="ignore").to_csv(
        out / "club.csv.gz", index=False
    )
    competitions.to_csv(out / "campionati.csv.gz", index=False)

    counts = table.groupby(["competition_id", "season"]).size().unstack(fill_value=0)
    with pd.option_context("display.width", 200, "display.max_rows", 100):
        print(counts.to_string(), end="\n\n")
    print(f"{len(table)} righe giocatore-stagione, {len(players)} giocatori, ", end="")
    print(f"{len(moves)} trasferimenti")
    print(f"Scritti in {out}/")


def _mercato_suggerisci(args: argparse.Namespace) -> None:
    data = market_data.load(args.dati)
    as_of = pd.Timestamp(args.data)
    model = market.train(data, range(args.da, args.ultima + 1))
    print("Modello di plausibilità (effetto di una deviazione standard sul log-odds):")
    print(model.coefficients().to_string(), end="\n\n")
    squads = rose.read(args.rose)
    needs, squad = market.needs_now(squads, data, as_of, args.ultima, args.finestra, args.stagione)
    candidates = market.candidates_now(
        squad, needs, data, model, as_of, args.ultima, args.per_ruolo, args.stagione
    )
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = f"{args.finestra}_{as_of.year}"
    needs.drop(columns=["profondita", "divario_grezzo"]).to_csv(
        out / f"fabbisogni_{tag}.csv", index=False
    )
    candidates.to_csv(out / f"candidati_{tag}.csv", index=False)
    top = needs[needs["rango"] <= 2][["club", "slot", "punteggio", "motivo"]]
    with pd.option_context("display.width", 200, "display.max_colwidth", 120):
        print(top.to_string(index=False), end="\n\n")
    print(f"Scritti {out}/fabbisogni_{tag}.csv e {out}/candidati_{tag}.csv")


def _mercato_verifica(args: argparse.Namespace) -> None:
    data = market_data.load(args.dati)
    ps, players, transfers = data.player_seasons, data.players, data.transfers
    train_seasons = range(args.da, args.prova)
    test_seasons = range(args.prova, args.a + 1)
    rows = []
    for window in ("gennaio", "estate"):
        result = needs_backtest.evaluate(ps, players, transfers, range(args.da, args.a + 1), window)
        train, test = result[result["season"] < args.prova], result[result["season"] >= args.prova]
        rows.append(
            {"finestra": window, "metodo": "fabbisogni", **needs_backtest.summary(test["rango"])}
        )
        base = needs_backtest.baseline_ranks(test, train)
        rows.append(
            {"finestra": window, "metodo": "ruoli più comprati", **needs_backtest.summary(base)}
        )
    print("Fabbisogni: in quale posizione della classifica dei fabbisogni cadono gli acquisti veri")
    print("(a caso: primo 12,5%, primi 2 25%, primi 3 37,5%)")
    with pd.option_context("display.width", 160, "display.float_format", "{:.3f}".format):
        print(pd.DataFrame(rows).to_string(index=False), end="\n\n")

    train = candidates_backtest.window_frames(ps, players, transfers, train_seasons)
    test = candidates_backtest.window_frames(ps, players, transfers, test_seasons, negatives=None)
    model = market.fit(train)
    rng = np.random.default_rng(0)
    methods = {
        "modello": model.score(test),
        "valore vicino al club": -test["rel_valore"].abs().to_numpy(),
        "a caso": rng.random(len(test)),
    }
    rows = []
    for name, score in methods.items():
        ranks = candidates_backtest.ranks(test, score)
        rows.append({"metodo": name, **candidates_backtest.summary(ranks)})
    pool = sum(len(needs_backtest.arrivals(transfers, needs_backtest.clubs_of_season(ps, s), s, w))
               for s in test_seasons for w in ("gennaio", "estate"))  # fmt: skip
    print(
        f"Candidati: rango degli acquisti veri tra i candidati dello stesso ruolo, {test_seasons}"
    )
    print(f"(acquisti da campionati coperti: {int(test['firmato'].sum())} su {pool})")
    with pd.option_context("display.width", 160, "display.float_format", "{:.3f}".format):
        print(pd.DataFrame(rows).to_string(index=False))
    expected = model.probability(test).sum()
    print(f"\nAcquisti attesi dal modello {expected:.0f}, veri {int(test['firmato'].sum())}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="xmercato")
    sub = parser.add_subparsers(dest="command", required=True)

    sim = sub.add_parser("simulate", help="Simulate the rest of a league season")
    sim.add_argument("--results", help="Path or URL of a football-data.co.uk CSV")
    sim.add_argument("--storico", help="Table from `xmercato storico` (enables past seasons)")
    sim.add_argument("--stagione", type=int, help="Season start year (with --storico)")
    sim.add_argument(
        "--modello", choices=sorted(forecast.CONFIGS), default="base",
        help="base: this season only; gol/xg: past seasons too (need --storico)",
    )  # fmt: skip
    sim.add_argument("--as-of", help="Only use matches up to this date (YYYY-MM-DD), for backtests")
    sim.add_argument("--n-sims", type=int, default=10_000)
    sim.add_argument("--shrinkage", type=float, default=None, help="Override the model's")
    sim.add_argument("--seed", type=int, default=None)
    sim.set_defaults(func=_simulate)

    squads = sub.add_parser("rose", help="Squad lists")
    squads_sub = squads.add_subparsers(dest="rose_command", required=True)
    seasons = sorted(rose.SERIE_A)

    bozza = squads_sub.add_parser("bozza", help="Draft squads from the Transfermarkt snapshot")
    bozza.add_argument("--out", required=True, help="Where to write the draft CSV")
    bozza.add_argument("--tm", help="Folder with the *.csv.gz tables (default: download them)")
    bozza.add_argument("--stagione", default=seasons[-1], choices=seasons)
    bozza.set_defaults(func=_rose_bozza)

    controlla = squads_sub.add_parser("controlla", help="Check a squad file")
    controlla.add_argument("file")
    controlla.add_argument("--stagione", default=seasons[-1], choices=seasons)
    controlla.set_defaults(func=_rose_controlla)

    riconcilia = squads_sub.add_parser(
        "riconcilia", help="Apply a list of current squads to the squad file"
    )
    riconcilia.add_argument("--lista", required=True, help="CSV with the current squads")
    riconcilia.add_argument("--file", default="rose/serie_a_2026_27.csv")
    riconcilia.add_argument("--tm", help="Folder with the Transfermarkt *.csv.gz tables")
    riconcilia.add_argument("--report", help="Where to write every decision, for review")
    riconcilia.add_argument("--stagione", default=seasons[-1], choices=seasons)
    riconcilia.set_defaults(func=_rose_riconcilia)

    storico = sub.add_parser("storico", help="Results, odds and xG for several seasons")
    storico.add_argument("--da", type=int, default=2014, help="First season (start year)")
    storico.add_argument("--a", type=int, required=True, help="Last season (start year)")
    storico.add_argument("--out", default="data/storico/serie_a.csv")
    storico.add_argument("--tiri", help="Understat shots archive (.rds); without it, no xG")
    storico.set_defaults(func=_storico)

    bt = sub.add_parser("backtest", help="Score the models on past seasons")
    bt.add_argument("--storico", default="data/storico/serie_a.csv")
    bt.add_argument("--da", type=int, default=2020, help="First season to test")
    bt.add_argument("--a", type=int, default=2025, help="Last season to test")
    bt.add_argument(
        "--modelli", nargs="+", choices=sorted(forecast.CONFIGS), default=["base", "gol", "xg"]
    )
    bt.add_argument("--n-sims", type=int, default=2000)
    bt.add_argument("--out", help="Folder for per-match and per-table details")
    bt.set_defaults(func=_backtest)

    mercato = sub.add_parser("mercato", help="Transfer market")
    mercato_sub = mercato.add_subparsers(dest="mercato_command", required=True)
    dati = mercato_sub.add_parser("dati", help="Player-season table from Transfermarkt match data")
    dati.add_argument("--out", default="data/mercato")
    dati.add_argument("--tm", help="Folder with the *.csv.gz tables (default: download them)")
    dati.add_argument("--da", type=int, default=2018, help="First season (start year)")
    dati.set_defaults(func=_mercato_dati)

    sug = mercato_sub.add_parser("suggerisci", help="Needs and candidates for a window")
    sug.add_argument("--dati", default="data/mercato", help="Output of `xmercato mercato dati`")
    sug.add_argument("--rose", default="rose/serie_a_2026_27.csv")
    sug.add_argument("--stagione", default="2026_27", choices=sorted(rose.SERIE_A))
    sug.add_argument("--finestra", default="gennaio", choices=["gennaio", "estate"])
    sug.add_argument("--data", default="2027-01-02", help="Opening date of the window")
    sug.add_argument("--da", type=int, default=2019, help="First season used for training")
    sug.add_argument("--ultima", type=int, default=2025, help="Last season with match data")
    sug.add_argument("--per-ruolo", type=int, default=40, help="Candidates per club and slot")
    sug.add_argument("--out", default="mercato")
    sug.set_defaults(func=_mercato_suggerisci)

    ver = mercato_sub.add_parser("verifica", help="Backtest of needs and candidates")
    ver.add_argument("--dati", default="data/mercato")
    ver.add_argument("--da", type=int, default=2019, help="First season")
    ver.add_argument("--prova", type=int, default=2023, help="First test season")
    ver.add_argument("--a", type=int, default=2025, help="Last season")
    ver.set_defaults(func=_mercato_verifica)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
