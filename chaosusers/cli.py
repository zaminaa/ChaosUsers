import argparse
import sys

from chaosusers import __version__


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
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
