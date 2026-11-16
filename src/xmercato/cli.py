"""Command line entry point: ``xmercato simulate ...``."""

from __future__ import annotations

import argparse

import pandas as pd

from xmercato.ingest import football_data
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

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
