"""Spanish and Portuguese transaction support with verified review tickets."""

import argparse
from dataclasses import asdict
import json
import os
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
    web.add_argument("--port", type=int,
                     help="Local default 8765; hosted default PORT environment value or 8080")
    web.add_argument("--hosted", action="store_true",
                     help="Opt in to public fictional DEMO mode behind trusted HTTPS termination")
    web.add_argument("--host", choices=("127.0.0.1", "0.0.0.0"),
                     help="Local mode requires 127.0.0.1; hosted default is 0.0.0.0")
    web.add_argument("--public-origin",
                     help="Canonical HTTPS public origin, or PUBLIC_ORIGIN environment value; hosted only")
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
        hosting = None
        if args.hosted:
            # Refuse private data/identity overrides before importing any loader.
            if args.cohort_run is not None or args.customer_id is not None or args.permission is not None:
                parser.error("hosted mode forbids --cohort-run, --customer-id and --permission")
            from bank_service.hosting import HostingConfig
            try:
                hosting = HostingConfig(
                    args.public_origin if args.public_origin is not None else os.environ.get("PUBLIC_ORIGIN"),
                    args.host if args.host is not None else "0.0.0.0",
                )
                if args.port is None:
                    value = os.environ.get("PORT", "8080")
                    if not value.isascii() or not value.isdecimal():
                        raise ValueError("invalid_port")
                    args.port = int(value)
                if not 1 <= args.port <= 65535:
                    raise ValueError("invalid_port")
            except ValueError:
                parser.error("hosted mode requires a canonical HTTPS PUBLIC_ORIGIN and a port from 1 to 65535")
        else:
            if args.public_origin is not None or args.host == "0.0.0.0":
                parser.error("--public-origin and binding 0.0.0.0 require --hosted")
            args.port = 8765 if args.port is None else args.port
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
            location = "local" if hosting is None else "hosted DEMO"
            print(f"Experimental {location} router {version}: guarded serving policy; "
                  "Spanish owner-reviewed; Portuguese accepted without fluent review.", flush=True)
        if hosting is not None:
            if router is None:
                serve(args.port, hosting=hosting)
            else:
                serve(args.port, hosting=hosting, router=router)
            return
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
    parser.print_help()


if __name__ == "__main__":
    main()
