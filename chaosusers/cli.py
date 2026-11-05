import argparse
import sys

import yaml

from chaosusers import __version__
from chaosusers.packs.loader import PackError, list_packs, load_pack


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (OSError, ValueError):
                pass
    parser = argparse.ArgumentParser(prog="chaosusers")
    parser.add_argument("--version", action="version", version=f"chaosusers {__version__}")
    sub = parser.add_subparsers(dest="command")
    packs = sub.add_parser("packs")
    packs_sub = packs.add_subparsers(dest="packs_command", required=True)
    packs_sub.add_parser("list")
    validate = packs_sub.add_parser("validate")
    validate.add_argument("pack")
    show = packs_sub.add_parser("show")
    show.add_argument("persona_id")
    show.add_argument("--pack", default="core-en")
    demo_bot = sub.add_parser("demo-bot")
    demo_bot.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    if args.command == "demo-bot":
        from chaosusers.demo.server import serve

        serve(args.port)
        return 0
    if args.command == "packs":
        try:
            return _packs(args)
        except PackError as exc:
            print(exc, file=sys.stderr)
            return 2
    return 0


def _packs(args: argparse.Namespace) -> int:
    if args.packs_command == "list":
        for meta in list_packs():
            pack = load_pack(meta.id)
            panel = len(pack.for_mode("panel"))
            gauntlet = len(pack.for_mode("gauntlet"))
            print(f"{meta.id}  {meta.version}  {meta.language}  {len(pack.personas)} ({panel}/{gauntlet})")
        return 0
    pack = load_pack(args.pack)
    if args.packs_command == "validate":
        panel = len(pack.for_mode("panel"))
        gauntlet = len(pack.for_mode("gauntlet"))
        print(f"OK {pack.meta.id}@{pack.meta.version}: {len(pack.personas)} personas ({panel} panel, {gauntlet} gauntlet)")
        return 0
    persona = pack.personas.get(args.persona_id)
    if persona is None:
        raise PackError(f"unknown persona {args.persona_id}")
    print(yaml.safe_dump(persona.model_dump(mode="json"), sort_keys=False, allow_unicode=True).rstrip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
