"""Codex interface: list pending prose, register an implementation, run pending."""
import argparse
import json

import store
from engine import run_pending


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("pending")
    commands.add_parser("run")
    register = commands.add_parser("implement")
    register.add_argument("id")
    register.add_argument("rule", help="Explicit JSON rule matching the current description")
    args = parser.parse_args()
    store.initialize()
    if args.command == "pending":
        result = [x for x in store.ideas() if not x["realize"]]
    elif args.command == "implement":
        store.register(args.id, json.loads(args.rule))
        result = {"registered": args.id}
    else:
        result = run_pending()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
