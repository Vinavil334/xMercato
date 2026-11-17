"""Command line entry point.

xmercato simulate --results ...      league table simulation
xmercato rose bozza --out ...        squad draft from the Transfermarkt snapshot
xmercato rose controlla FILE         check a hand-maintained squad file
xmercato rose riconcilia --lista ... apply a list of current squads to the squad file
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from xmercato import rose, rose_sync
from xmercato.ingest import football_data, transfermarkt
from xmercato.models import poisson
from xmercato.sim import season


def _simulate(args: argparse.Namespace) -> None:
    results = football_data.load_results(args.results)
    teams = sorted(set(results["home"]) | set(results["away"]))
    if args.as_of:
        results = results[results["date"] <= pd.Timestamp(args.as_of)]

    strengths = poisson.fit(results, teams=teams, shrinkage=args.shrinkage)
    table = season.simulate(strengths, results, n_sims=args.n_sims, seed=args.seed)
    summary = season.summarise(table)

    todo = len(season.remaining_fixtures(results, teams))
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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="xmercato")
    sub = parser.add_subparsers(dest="command", required=True)

    sim = sub.add_parser("simulate", help="Simulate the rest of a league season")
    sim.add_argument("--results", required=True, help="Path or URL of a football-data.co.uk CSV")
    sim.add_argument("--as-of", help="Only use matches up to this date (YYYY-MM-DD), for backtests")
    sim.add_argument("--n-sims", type=int, default=10_000)
    sim.add_argument("--shrinkage", type=float, default=2.0)
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

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
