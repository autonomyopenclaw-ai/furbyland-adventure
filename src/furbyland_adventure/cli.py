"""Command line: auth, start, advance, status."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from furbyland_adventure.auth import run_auth
from furbyland_adventure.config import load_settings
from furbyland_adventure.dotenv import load_dotenv
from furbyland_adventure.engine import Adventure, render_status, require_user
from furbyland_adventure.errors import AdventureError
from furbyland_adventure.state import StateStore
from furbyland_adventure.writer import build_writer
from furbyland_adventure.x_client import build_x_client


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except AdventureError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


def console_main() -> None:
    sys.exit(main())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adventure",
        description=(
            "Post a choose-your-own-adventure on X and continue it from replies. "
            "Every command accepts --dry-run."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Post the opening chapter from a premise file.")
    start.add_argument("--premise", help="Premise file. Defaults to ADVENTURE_PREMISE_PATH.")
    start.add_argument("--dry-run", action="store_true", help="Print the chapter. Do not post.")
    start.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing story in the state file.",
    )
    start.set_defaults(func=cmd_start)

    advance = sub.add_parser("advance", help="Read replies and post the next chapter.")
    advance.add_argument("--dry-run", action="store_true", help="Read and print. Do not post.")
    advance.set_defaults(func=cmd_advance)

    status = sub.add_parser("status", help="Show the saved chapter, post, and summary.")
    status.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the local state file and do not contact X.",
    )
    status.set_defaults(func=cmd_status)

    auth = sub.add_parser("auth", help="Authorize the adventure account with a PIN.")
    auth.add_argument("--pin", help="PIN from X. If omitted, you are prompted.")
    auth.set_defaults(func=cmd_auth)
    return parser


def cmd_start(args: argparse.Namespace) -> int:
    settings = load_settings()
    premise_path = Path(args.premise) if args.premise else settings.premise_path
    premise = _read_premise(premise_path)
    store = StateStore(settings.state_path)
    writer = build_writer(settings)
    client = None if args.dry_run else _ready_client(settings)
    result = Adventure(settings, client, writer, store).start(
        premise,
        dry_run=args.dry_run,
        force=args.force,
    )
    _print_result(result)
    return 0


def cmd_advance(args: argparse.Namespace) -> int:
    settings = load_settings()
    settings.require_credentials()
    store = StateStore(settings.state_path)
    writer = build_writer(settings)
    result = Adventure(settings, build_x_client(settings), writer, store).advance(
        dry_run=args.dry_run
    )
    _print_result(result)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    settings = load_settings()
    state = StateStore(settings.state_path).load()
    print(render_status(settings, state))
    if args.dry_run:
        print("Account check: skipped (--dry-run).")
        return 0
    missing = settings.missing_credentials()
    if missing:
        print("Account check: skipped. Missing " + ", ".join(missing) + ".")
        return 0
    me = require_user(build_x_client(settings), settings.username)
    print(f"Authenticated as @{me.username}: matches ADVENTURE_USERNAME.")
    return 0


def cmd_auth(args: argparse.Namespace) -> int:
    settings = load_settings()
    run_auth(settings, pin=args.pin)
    return 0


def _ready_client(settings):
    settings.require_credentials()
    return build_x_client(settings)


def _read_premise(path: Path) -> str:
    from furbyland_adventure.errors import ConfigError

    if not path.is_file():
        raise ConfigError(
            f"Premise file not found: {path}. Edit premises/sample.md, "
            "or pass --premise path/to/your-story.md."
        )
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ConfigError(f"Premise file is empty: {path}")
    return text


def _print_result(result) -> None:
    print(result.message)
    if not result.posts:
        return
    print()
    for index, post in enumerate(result.posts, start=1):
        label = f"Post {index}" if len(result.posts) > 1 else "Post"
        print(f"{label} ({len(post)} characters):")
        print(post)
        print()
    handle = result.username
    for post_id in result.post_ids:
        if handle:
            print(f"https://x.com/{handle}/status/{post_id}")
        else:
            print(f"https://x.com/i/status/{post_id}")
