import pytest

from chaosusers.llm.jsonout import extract_json


def test_plain_object():
    assert extract_json('{"ok": true}') == {"ok": True}


def test_fenced_object():
    text = '```json\n{"ok": 1}\n```'
    assert extract_json(text) == {"ok": 1}


def test_prose_around_object():
    assert extract_json('Sure! {"ok": 1} hope this helps') == {"ok": 1}


def test_braces_inside_strings():
    assert extract_json('{"message": "use {curly}"}') == {"message": "use {curly}"}


def test_persian_text():
    assert extract_json('{"msg": "سلام"}') == {"msg": "سلام"}


def test_rejects_array():
    with pytest.raises(ValueError):
        extract_json("[1,2]")


def test_rejects_prose():
    with pytest.raises(ValueError):
        extract_json("no json here")
