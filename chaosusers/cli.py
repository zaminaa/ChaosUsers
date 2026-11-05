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
    gauntlet = sub.add_parser("gauntlet")
    _add_run_flags(gauntlet)
    gauntlet.add_argument("--target", default="demo")
    gauntlet.add_argument("--scenario", default="demo")
    report = sub.add_parser("report")
    report.add_argument("run_dir")
    panel = sub.add_parser("panel")
    panel.add_argument("artifact")
    panel.add_argument("--kind", dest="artifact_kind", choices=["page", "text", "botscript"], default=None)
    _add_run_flags(panel)
    args = parser.parse_args(argv)
    if args.command == "report":
        from pathlib import Path

        from chaosusers.report.render import write_reports

        write_reports(Path(args.run_dir))
        print(f"Badge: ![chaosusers]({args.run_dir}/badge.svg)")
        return 0
    if args.command == "panel":
        from chaosusers.config import ConfigError
        from chaosusers.panel.runner import plan_panel, run_panel

        try:
            cfg = _run_config(args, "panel")
        except ConfigError as exc:
            print(exc, file=sys.stderr)
            return 2
        if cfg.dry_run:
            planned = plan_panel(cfg)
            print(f"Sections: {planned['sections']}")
            print(f"Worst-case cost: ${planned['worst_case_usd']:.2f} (cap ${cfg.max_usd:.2f})")
            return 0
        try:
            path = run_panel(cfg)
        except ConfigError as exc:
            print(exc, file=sys.stderr)
            return 2
        return _finish(path, cfg)
    if args.command == "gauntlet":
        from chaosusers.config import ConfigError
        from chaosusers.gauntlet.runner import plan_gauntlet, run_gauntlet

        try:
            cfg = _run_config(args, "gauntlet")
        except ConfigError as exc:
            print(exc, file=sys.stderr)
            return 2
        if cfg.dry_run:
            planned = plan_gauntlet(cfg)
            print(f"Worst-case cost: ${planned['worst_case_usd']:.2f} (cap ${cfg.max_usd:.2f})")
            print(f"personas: {', '.join(planned['personas'])}")
            print(f"conversations: {planned['conversations']}  max LLM calls: {planned['max_llm_calls']}")
            return 0
        try:
            path = run_gauntlet(cfg)
        except ConfigError as exc:
            print(exc, file=sys.stderr)
            return 2
        return _finish(path, cfg)
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


def _add_run_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pack", default="core-en")
    parser.add_argument("--personas", default=None)
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--judge-samples", type=int, default=3)
    parser.add_argument("--max-usd", type=float, default=1.0)
    parser.add_argument("--max-tokens", type=int, default=400_000)
    parser.add_argument("--max-turns", type=int, default=12)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--provider", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--judge-model", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--allow-unpriced", action="store_true")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--replay", default=None)
    parser.add_argument("--script", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-under", choices=["A", "B", "C", "D"], default=None)
    parser.add_argument("--out", default="chaosusers-runs")
    parser.add_argument("--open", action="store_true")


def _run_config(args: argparse.Namespace, mode: str):
    from pathlib import Path

    from chaosusers.config import RunConfig

    return RunConfig(
        mode=mode,
        pack=args.pack,
        personas=args.personas.split(",") if args.personas else None,
        repeats=args.repeats,
        judge_samples=args.judge_samples,
        max_usd=args.max_usd,
        max_tokens=args.max_tokens,
        max_turns=args.max_turns,
        concurrency=args.concurrency,
        seed=args.seed,
        provider=args.provider,
        model=args.model,
        judge_model=args.judge_model,
        base_url=args.base_url,
        allow_unpriced=args.allow_unpriced,
        replay=Path(args.replay) if args.replay else None,
        script=Path(args.script) if args.script else None,
        out_dir=Path(args.out),
        target=getattr(args, "target", None),
        scenario=getattr(args, "scenario", None),
        artifact=getattr(args, "artifact", None),
        fail_under=args.fail_under,
        dry_run=args.dry_run,
        open_report=args.open,
    )


def _finish(path, cfg) -> int:
    import json

    scores = json.loads((path / "scores.json").read_text(encoding="utf-8"))
    grade = scores.get("grade")
    order = ["A", "B", "C", "D", "F"]
    if cfg.fail_under and (grade is None or order.index(grade) > order.index(cfg.fail_under)):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
