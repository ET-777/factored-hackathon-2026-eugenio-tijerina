"""Local workflow status and synthetic demonstrations; no network or model calls."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys


def main() -> None:
    # Windows redirects may otherwise use a legacy code page and lose ES/PT text.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command")
    demo = commands.add_parser("demo", help="Run a synthetic, scripted local workflow")
    demo.add_argument("--language", choices=("es", "pt"), default="es")
    demo.add_argument("--scenario", choices=("all", "inquiry", "intake", "handoff", "safety"), default="all")
    demo.add_argument("--db", type=Path, help="Optional local SQLite path; omitted means temporary storage")
    web = commands.add_parser("web", help="Start the local bilingual review UI with fictional data")
    web.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.command == "web":
        from bank_service.web_app import serve
        serve(args.port)
        return
    if args.command == "demo":
        from bank_service.demo import run_demo
        result = run_demo(language=args.language, scenario=args.scenario, db_path=args.db)
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return
    print(json.dumps({
        "status": "local_structured_workflow",
        "languages": ["es", "pt"],
        "banking_actions": "simulated_only",
        "model_implemented": False,
        "input_mode": "structured_commands_or_keyword_routing_and_explicit_confirmation",
        "workflow_implemented": True,
        "evaluation_run": False,
        "web_interface": "local_loopback_demo",
        "web_command": "python -B -m bank_service web",
        "demo_command": "python -B -m bank_service demo --language es",
    }, indent=2))


if __name__ == "__main__":
    main()
