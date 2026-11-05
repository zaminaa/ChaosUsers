from pathlib import Path


def data_root() -> Path:
    pkg = Path(__file__).parent / "_data"
    return pkg if pkg.exists() else Path(__file__).resolve().parents[1]


def resolve_data_path(p: str) -> Path:
    path = Path(p)
    if path.is_absolute() or path.exists():
        return path
    return data_root() / p
