import hashlib

from jinja2 import Environment, StrictUndefined

from chaosusers.paths import data_root


def render(name: str, **ctx) -> tuple[str, str]:
    path = data_root() / "prompts" / f"{name}.md.j2"
    env = Environment(undefined=StrictUndefined, autoescape=False)
    rendered = env.from_string(path.read_text(encoding="utf-8")).render(**ctx)
    system, user = rendered.split("---USER---", 1)
    return system.rstrip("\n"), user.lstrip("\n")


def prompt_hashes() -> dict[str, str]:
    hashes = {}
    for path in sorted((data_root() / "prompts").glob("*.md.j2")):
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes
