import copy
import hashlib
import re
from pathlib import Path

import yaml
from pydantic import ValidationError

from chaosusers.packs.schema import BehaviorClass, Lexicon, Pack, PackMeta, PersonaSpec
from chaosusers.paths import data_root

_EMAIL = re.compile(r"\S+@\S+\.\w+")
_URL = re.compile(r"https?://")
_PHONE = re.compile(r"\+?\d[\d\s-]{8,}\d")


class PackError(Exception):
    pass


def load_taxonomy(path: Path | None = None) -> dict[str, BehaviorClass]:
    taxonomy_path = path or data_root() / "packs" / "taxonomy.yaml"
    data = _read_yaml(taxonomy_path)
    classes = [BehaviorClass.model_validate(row) for row in data["classes"]]
    return {item.id: item for item in classes}


def list_packs() -> list[PackMeta]:
    root = data_root() / "packs"
    if not root.is_dir():
        return []
    metas = []
    for pack_yaml in sorted(root.glob("*/pack.yaml")):
        metas.append(PackMeta.model_validate(_read_yaml(pack_yaml)))
    return metas


def load_pack(name_or_path: str) -> Pack:
    meta, lexicon, personas, roots = _compose(_resolve_pack_dir(name_or_path), [])
    taxonomy = load_taxonomy()
    built: dict[str, PersonaSpec] = {}
    for persona_id, (source, raw) in personas.items():
        try:
            spec = PersonaSpec.model_validate(raw)
        except ValidationError as exc:
            raise PackError(f"{source}: {exc}") from exc
        _validate_persona(spec, taxonomy, meta, source)
        built[persona_id] = spec
    return Pack(meta=meta, lexicon=lexicon, personas=built, sha256=_pack_sha(roots))


def deep_merge(base: dict, over: dict) -> dict:
    merged = copy.deepcopy(base)
    for key, value in over.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _compose(pack_dir: Path, stack: list[str]):
    pack_yaml = pack_dir / "pack.yaml"
    if not pack_yaml.is_file():
        raise PackError(f"{pack_dir}: pack.yaml not found")
    _scan_tree(pack_dir)
    meta = PackMeta.model_validate(_read_yaml(pack_yaml))
    if meta.id in stack:
        raise PackError(f"{pack_dir}: extends cycle involving {meta.id}")
    lexicon_path = pack_dir / "lexicon.yaml"
    lexicon = Lexicon.model_validate(_read_yaml(lexicon_path)) if lexicon_path.is_file() else None
    personas = _raw_personas(pack_dir)
    roots = [pack_dir]
    if meta.extends:
        _base_meta, base_lexicon, base_personas, base_roots = _compose(
            _resolve_extends(pack_dir, meta.extends), stack + [meta.id]
        )
        merged = dict(base_personas)
        for persona_id, (source, raw) in personas.items():
            if persona_id in base_personas:
                merged[persona_id] = (source, deep_merge(base_personas[persona_id][1], raw))
            else:
                merged[persona_id] = (source, raw)
        personas = merged
        roots = base_roots + roots
        if lexicon is None:
            lexicon = base_lexicon
    if lexicon is None:
        raise PackError(f"{pack_dir}: lexicon.yaml missing")
    return meta, lexicon, personas, roots


def _validate_persona(spec: PersonaSpec, taxonomy: dict[str, BehaviorClass], meta: PackMeta, source: Path) -> None:
    if spec.behavior_class not in taxonomy:
        raise PackError(f"{source.name}: unknown behavior class {spec.behavior_class}")
    if spec.language not in meta.language_instructions:
        raise PackError(f"{source.name}: language {spec.language} is not in language_instructions")
    if spec.gauntlet is not None:
        drift = spec.gauntlet.fact_drift
        patience = spec.gauntlet.patience
        if not 0 <= drift <= 1:
            raise PackError(f"{source.name}: fact_drift out of range")
        if not patience.angry_below <= patience.frustrated_below <= patience.start:
            raise PackError(f"{source.name}: patience thresholds are out of order")
        for operator in spec.gauntlet.operators:
            if not 0 <= operator.p <= 1 or (operator.rate is not None and not 0 <= operator.rate <= 1):
                raise PackError(f"{source.name}: operator probability out of range")
    problems = _fidelity_problems(spec)
    if problems:
        raise PackError(f"{source.name}: example_utterance failed fidelity: {', '.join(problems)}")


def _fidelity_problems(spec: PersonaSpec) -> list[str]:
    # shortcut: utterance check starts once engine.fidelity exists (T10)
    try:
        from chaosusers.engine.fidelity import check_fidelity
    except ImportError:
        return []
    return check_fidelity(spec.voice.example_utterance, spec)


def _raw_personas(pack_dir: Path) -> dict[str, tuple[Path, dict]]:
    persona_dir = pack_dir / "personas"
    if not persona_dir.is_dir():
        return {}
    found = {}
    for path in sorted(persona_dir.glob("*.yaml")):
        found[path.stem] = (path, _read_yaml(path) or {})
    return found


def _resolve_pack_dir(name_or_path: str) -> Path:
    path = Path(name_or_path)
    if path.is_absolute() or path.exists():
        return path
    return data_root() / "packs" / name_or_path


def _resolve_extends(pack_dir: Path, extends: str) -> Path:
    sibling = pack_dir.parent / extends
    if sibling.is_dir():
        return sibling
    return data_root() / "packs" / extends


def _scan_tree(pack_dir: Path) -> None:
    for path in pack_dir.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if _EMAIL.search(text):
            raise PackError(f"{path.name}: email address is not allowed")
        if _URL.search(text):
            raise PackError(f"{path.name}: URL is not allowed")
        if _PHONE.search(text):
            raise PackError(f"{path.name}: phone number is not allowed")


def _pack_sha(roots: list[Path]) -> str:
    digest = hashlib.sha256()
    blobs: list[tuple[str, bytes]] = []
    for directory in roots:
        for path in directory.rglob("*"):
            if path.is_file():
                rel = f"{directory.name}/{path.relative_to(directory).as_posix()}"
                blobs.append((rel, path.read_bytes()))
    for name, blob in sorted(blobs):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob)
    return digest.hexdigest()


def _read_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))
