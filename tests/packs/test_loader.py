import shutil
from pathlib import Path

import pytest

from chaosusers.cli import main
from chaosusers.packs.loader import PackError, deep_merge, load_pack

FIXTURES = Path("tests/fixtures/packs")


def test_overlay_overrides_utterance_and_inherits_gauntlet():
    pack = load_pack(str(FIXTURES / "overlay"))
    persona = pack.personas["tiny"]
    assert persona.voice.example_utterance == "changed"
    assert persona.gauntlet is not None
    assert persona.gauntlet.patience.start == 6
    assert persona.voice.register == "terse"


def test_missing_class_names_the_file():
    with pytest.raises(PackError, match="bad.yaml"):
        load_pack(str(FIXTURES / "bad-class"))


def test_email_is_rejected():
    with pytest.raises(PackError, match="email"):
        load_pack(str(FIXTURES / "bad-pii"))


def test_sha256_changes_when_a_file_changes(tmp_path: Path):
    copied = tmp_path / "base"
    shutil.copytree(FIXTURES / "base", copied)
    before = load_pack(str(copied)).sha256
    utterance = copied / "personas" / "tiny.yaml"
    utterance.write_text(utterance.read_text(encoding="utf-8").replace("keep", "kept"), encoding="utf-8")
    assert load_pack(str(copied)).sha256 != before


def test_deep_merge_does_not_mutate_base():
    base = {"voice": {"example_utterance": "keep", "register": "terse"}}
    merged = deep_merge(base, {"voice": {"example_utterance": "changed"}})
    assert base["voice"]["example_utterance"] == "keep"
    assert merged["voice"] == {"example_utterance": "changed", "register": "terse"}


def test_validate_and_show_cli(capsys):
    assert main(["packs", "validate", str(FIXTURES / "base")]) == 0
    assert "OK base@0.1.0: 1 personas (1 panel, 1 gauntlet)" in capsys.readouterr().out
    assert main(["packs", "show", "tiny", "--pack", str(FIXTURES / "overlay")]) == 0
    assert "example_utterance: changed" in capsys.readouterr().out
    assert main(["packs", "validate", str(FIXTURES / "bad-pii")]) == 2
