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
    demo = sub.add_parser("demo")
    demo.add_argument("which", nargs="?", choices=["gauntlet", "panel"], default="gauntlet")
    demo.add_argument("--no-open", action="store_true")
    demo.add_argument("--pace", type=float, default=0.0)
    demo.add_argument("--out", default="chaosusers-runs")
    demo_bot = sub.add_parser("demo-bot")
    demo_bot.add_argument("--port", type=int, default=8787)
    gauntlet = sub.add_parser("gauntlet")
    _add_run_flags(gauntlet)
    gauntlet.add_argument("--target", default="demo")
    gauntlet.add_argument("--scenario", default="demo")
    calibrate = sub.add_parser("calibrate")
    calibrate.add_argument("--rubric", default="gauntlet_v1")
    calibrate.add_argument("--script", required=True)
    calibrate.add_argument("--judge-model", default="gpt-4.1-mini")
    calibrate.add_argument("--samples", type=int, default=1)
    verify = sub.add_parser("verify")
    verify.add_argument("run_dir")
    verify.add_argument("--observed", required=True)
    report = sub.add_parser("report")
    report.add_argument("run_dir")
    panel = sub.add_parser("panel")
    panel.add_argument("artifact")
    panel.add_argument("--kind", dest="artifact_kind", choices=["page", "text", "botscript"], default=None)
    _add_run_flags(panel)
    args = parser.parse_args(argv)
    if args.command == "calibrate":
        from pathlib import Path

        from chaosusers.llm.budget import Budget
        from chaosusers.llm.client import LLMClient
        from chaosusers.llm.testing import ScriptedProvider
        from chaosusers.record.calibrate import calibrate

        result = calibrate(
            args.rubric,
            LLMClient(ScriptedProvider.from_yaml(Path(args.script)), Budget(1, 400_000, 0, 0), None),
            args.judge_model,
            args.samples,
        )
        for dim, score in result["per_dim"].items():
            print(f"{dim:<20} {score:.2f}")
        print(result)
        return 0
    if args.command == "demo":
        return _demo(args)
    if args.command == "verify":
        import json
        from pathlib import Path

        import yaml

        from chaosusers.record.schema import Observed
        from chaosusers.record.verify import verify_run

        run_dir = Path(args.run_dir)
        observed = Observed.model_validate(yaml.safe_load(Path(args.observed).read_text(encoding="utf-8")))
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        if observed.run_id != manifest["run_id"]:
            print(f"WARNING: observed run_id {observed.run_id} differs from {manifest['run_id']}", file=sys.stderr)
        result = verify_run(run_dir, Path(args.observed))
        predictions = json.loads((run_dir / "predictions.json").read_text(encoding="utf-8"))["predictions"]
        claims = {item["id"]: item["claim"] for item in predictions}
        print(f"{'ID':<8}{'KIND':<12}{'STATUS':<12}CLAIM")
        for row, pred in zip(result.results, predictions, strict=True):
            print(f"{row.id:<8}{pred['kind']:<12}{row.status:<12}{claims[row.id]}")
        if not result.receipt_intact:
            print("WARNING: predictions.json changed after the run", file=sys.stderr)
        precision = "n/a" if result.precision is None else f"{result.confirmed}/{result.confirmed + result.refuted} ({result.precision:.0%})"
        print(f"Precision: {precision} · receipt intact: {'yes' if result.receipt_intact else 'no'}")
        (run_dir / "verification.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        from chaosusers.report.render import write_reports

        write_reports(run_dir)
        return 0
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


def _demo(args: argparse.Namespace) -> int:
    import json
    import time
    from pathlib import Path

    from chaosusers.config import RunConfig
    from chaosusers.paths import data_root, resolve_data_path

    name = "demo-gauntlet" if args.which == "gauntlet" else "demo-panel"
    meta = json.loads((data_root() / "cassettes" / f"{name}.meta.json").read_text(encoding="utf-8"))
    cassette = data_root() / "cassettes" / f"{name}.jsonl"
    scripted = bool(meta.get("scripted"))
    label = "SCRIPTED DEMO (not a real model run)" if scripted else f"REPLAY of a run recorded {meta.get('recorded_at')} with {meta.get('model')} ($0, no API key)"
    print(f"ChaosUsers 0.1.0 · {args.which} · {label}")

    def progress(line: str) -> None:
        print(line)
        if args.pace:
            time.sleep(args.pace)

    cfg = RunConfig(
        mode="gauntlet" if args.which == "gauntlet" else "panel",
        replay=cassette,
        script=Path("scripted") if scripted else None,
        seed=meta.get("seed", 33),
        repeats=meta.get("repeats", 2),
        judge_samples=meta.get("judge_samples", 1),
        max_turns=meta.get("max_turns", 5),
        model=meta.get("model"),
        judge_model=meta.get("judge_model"),
        out_dir=Path(args.out),
        target="demo",
        scenario="demo",
        artifact=str(resolve_data_path("examples/artifacts/acme-landing.html")),
        concurrency=1,
    )
    if args.which == "gauntlet":
        from chaosusers.gauntlet.runner import run_gauntlet

        path = run_gauntlet(cfg, progress)
    else:
        from chaosusers.panel.runner import run_panel

        path = run_panel(cfg, progress)
    if not args.no_open:
        print(f"Open {path / 'report.html'}")
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
