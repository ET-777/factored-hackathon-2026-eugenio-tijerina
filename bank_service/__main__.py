"""Local UI with optional offline learned routing; no external provider calls."""

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
    web = commands.add_parser("web", help="Start the loopback review UI; fictional records by default")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--router", choices=("keyword", "learned-preview", "learned-preview-v2"),
                     default="keyword",
                     help="Experimental learned previews use only fixed authored TRAIN artifacts")
    web.add_argument("--cohort-run", type=Path,
                     help="Trusted startup path to an existing bounded private cohort")
    web.add_argument("--customer-id",
                     help="Fixed local test identity from that private cohort; not bank authentication")
    web.add_argument("--permission", action="append",
                     choices=("transaction:read", "intake:create_simulated", "handoff:create_simulated"),
                     help="Repeat to grant explicit private-mode permissions; default is transaction:read")
    args = parser.parse_args()
    if args.command == "web":
        from bank_service.web_app import PrivateCohortConfig, serve
        router = None
        if args.router in ("learned-preview", "learned-preview-v2"):
            from bank_service.route_loader import load_preview_router, load_short_preview_router
            try:
                router = (load_short_preview_router() if args.router == "learned-preview-v2"
                          else load_preview_router())
            except ValueError:
                print("Learned preview startup refused.", file=sys.stderr)
                raise SystemExit(1) from None
            version = "v2 short-message candidate" if args.router == "learned-preview-v2" else "v1"
            print(f"Experimental local router {version}: authored draft training; "
                  "language review pending.", flush=True)
        if args.cohort_run is None:
            if args.customer_id is not None or args.permission is not None:
                parser.error("--customer-id and --permission require --cohort-run")
            if router is None:
                serve(args.port)
            else:
                serve(args.port, router=router)
            return
        if not isinstance(args.customer_id, str) or not args.customer_id.strip():
            parser.error("--cohort-run requires a nonempty --customer-id")
        from bank_service.access import Permission
        from bank_service.cohort_repository import CohortLoadError, load_private_cohort
        try:
            permissions = frozenset(Permission(value) for value in
                                    (args.permission or [Permission.READ_TRANSACTION.value]))
            config = PrivateCohortConfig(
                records=load_private_cohort(args.cohort_run),
                customer_id=args.customer_id,
                permissions=permissions,
            )
        except (CohortLoadError, ValueError, OSError):
            # Never include paths, identities, record values or loader exceptions.
            print("Private cohort startup refused.", file=sys.stderr)
            raise SystemExit(1) from None
        if router is None:
            serve(args.port, config=config)
        else:
            serve(args.port, config=config, router=router)
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
        "model_implemented": True,
        "learned_component_stage": "experimental_train_only_preview_not_evaluated",
        "input_mode": "keyword_default_or_learned_preview_and_explicit_confirmation",
        "workflow_implemented": True,
        "evaluation_run": False,
        "web_interface": "local_loopback_demo",
        "web_command": "python -B -m bank_service web",
        "demo_command": "python -B -m bank_service demo --language es",
    }, indent=2))


if __name__ == "__main__":
    main()
