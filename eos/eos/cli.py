"""Command-line entry point: run a simulation and print the EHS report.

    python -m eos.cli --ticks 240 --seed 7 --verbose
"""
from __future__ import annotations

import argparse
import json

from .enterprise_factory import build_default_enterprise
from .engines.chaos_engine import ChaosEngine
from .ops.operator import RuleBasedOperator
from .simulation import Simulator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an EOS simulation.")
    parser.add_argument("--ticks", type=int, default=240,
                        help="number of 30-min ticks to simulate (240 = 5 days)")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--chaos", type=float, default=0.08,
                        help="per-tick probability of a random fault")
    parser.add_argument("--no-preventive", action="store_true",
                        help="disable the operator's preventive maintenance")
    parser.add_argument("--verbose", action="store_true",
                        help="print a per-tick summary line")
    args = parser.parse_args(argv)

    enterprise = build_default_enterprise()
    operator = RuleBasedOperator(preventive=not args.no_preventive)
    chaos = ChaosEngine(seed=args.seed, probability=args.chaos)
    sim = Simulator(enterprise, operator=operator, chaos=chaos, seed=args.seed)

    for _ in range(args.ticks):
        log = sim.step()
        if args.verbose:
            print(
                f"t{log.tick:04d} {log.phase:<8} load={log.load:<4} "
                f"up={log.up} deg={log.degraded} down={log.down} "
                f"faults={log.active_faults} tickets={log.open_tickets} "
                f"cmds={log.commands}"
            )

    print("\n=== Enterprise Health Score ===")
    print(json.dumps(sim.ledger.report(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
