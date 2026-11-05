import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

_MARKER = re.compile(r"\[[^\]]+\]")


class Section(BaseModel):
    id: str
    title: str
    text: str
    word_count: int


class Artifact(BaseModel):
    source: str
    kind: str
    title: str
    sha256: str
    sections: list[Section]
    truncated: bool
    total_words: int


def load_artifact(src: str, kind: str | None = None, max_chars: int = 30_000, fetch=None) -> Artifact:
    detected = kind or _kind(src)
    if detected == "page" and src.startswith(("http://", "https://")):
        html, final = _fetch(src, fetch)
        sections, title = _parse_html(html)
        raw = html
        source = final
    elif detected == "page":
        path = Path(src)
        raw = path.read_text(encoding="utf-8")
        sections, title = _parse_html(raw)
        source = src
    elif detected == "botscript":
        raw = Path(src).read_text(encoding="utf-8")
        sections, title = _parse_botscript(raw)
        source = src
    else:
        raw = Path(src).read_text(encoding="utf-8")
        sections, title = _parse_text(raw)
        source = src
    sections, truncated = _cap(sections, max_chars)
    total = sum(section.word_count for section in sections)
    return Artifact(
        source=source, kind=detected, title=title or sections[0].title if sections else src,
        sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(), sections=sections,
        truncated=truncated, total_words=total,
    )


def visible_text(section: Section, reading) -> str:
    if reading.mode != "skim" or not reading.words_per_section:
        return section.text
    words = []
    markers = []
    for part in re.split(r"(\[[^\]]+\])", section.text):
        if part.startswith("[") and part.endswith("]"):
            markers.append(part)
        else:
            words.extend(part.split())
    kept = words[: reading.words_per_section]
    text = " ".join(kept + markers)
    if len(words) > reading.words_per_section:
        text += " …"
    return text.strip()


def _kind(src: str) -> str:
    if src.startswith(("http://", "https://")) or src.lower().endswith((".html", ".htm")):
        return "page"
    if src.lower().endswith((".yaml", ".yml")):
        import yaml
        data = yaml.safe_load(Path(src).read_text(encoding="utf-8")) or {}
        if isinstance(data, dict) and data.get("kind") == "botscript":
            return "botscript"
    return "text"


def _fetch(url: str, fetch) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"unsupported URL scheme: {parsed.scheme}")
    if fetch is not None:
        body = fetch(url)
        return body, url
    response = httpx.get(
        url, follow_redirects=True, timeout=20,
        headers={"User-Agent": "ChaosUsers/0.1 (+https://github.com/zaminaa/ChaosUsers)"},
    )
    response.raise_for_status()
    if len(response.content) > 2_000_000:
        raise ValueError("response is larger than 2 MB")
    return response.text, str(response.url)


def _cap(sections: list[Section], max_chars: int) -> tuple[list[Section], bool]:
    kept = []
    used = 0
    for section in sections:
        if used and used + len(section.text) > max_chars:
            return kept, True
        kept.append(section)
        used += len(section.text)
        if used > max_chars:
            return kept, True
    return kept, False


def _sections(chunks: list[tuple[str, list[str]]], fallback: str) -> tuple[list[Section], str]:
    if not chunks:
        chunks = [(fallback, [])]
    sections = []
    for index, (title, parts) in enumerate(chunks, start=1):
        text = " ".join(part.strip() for part in parts if part and part.strip())
        text = re.sub(r"\s+", " ", text).strip()
        sections.append(Section(id=f"S{index}", title=title.strip(), text=text, word_count=len(text.split())))
    return sections, sections[0].title


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[tuple[str, list[str]]] = []
        self.parts: list[str] = []
        self.title = "Top of page"
        self.skip = 0
        self.capture = None
        self.buf = []
        self.label = []
        self.in_label = False
        self.label_required = False
        self.checkbox = False
        self.checkbox_checked = False

    def handle_starttag(self, tag, attrs) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        if tag in {"script", "style", "noscript", "svg", "head"}:
            self.skip += 1
            return
        if self.skip:
            return
        if tag == "footer":
            self._flush("Footer")
        if tag in {"h1", "h2", "h3"}:
            self.capture = "heading"
            self.buf = []
        elif tag == "button" or (tag == "input" and attr.get("type", "").lower() == "submit"):
            self.capture = "button"
            self.buf = [attr.get("value", "")]
        elif tag == "a":
            role = attr.get("role", "")
            css = attr.get("class", "")
            self.capture = "button" if role == "button" or "button" in css.split() else "link"
            self.buf = []
        elif tag == "label":
            self.in_label = True
            self.label = []
            self.label_required = "required" in attr
            self.checkbox = False
            self.checkbox_checked = False
        elif tag == "input" and self.in_label and attr.get("type", "").lower() == "checkbox":
            self.checkbox = True
            self.checkbox_checked = "checked" in attr
        elif tag == "input" and self.in_label and "required" in attr:
            self.label_required = True
        elif tag == "li":
            self.parts.append(" ")

    def handle_endtag(self, tag) -> None:
        if tag in {"script", "style", "noscript", "svg", "head"} and self.skip:
            self.skip -= 1
            return
        if self.skip:
            return
        if tag in {"h1", "h2", "h3"} and self.capture == "heading":
            self._flush(" ".join("".join(self.buf).split()))
            self.capture = None
        elif tag in {"button", "a"} and self.capture in {"button", "link"}:
            text = " ".join("".join(self.buf).split())
            if self.capture == "button":
                self.parts.append(f"[BUTTON: {text}]")
            else:
                self.parts.append(text)
            self.capture = None
        elif tag == "label" and self.in_label:
            text = " ".join("".join(self.label).split())
            if self.checkbox and self.checkbox_checked:
                self.parts.append(f"[CHECKBOX pre-ticked: {text}]")
            else:
                if self.label_required and "(required" not in text.lower():
                    text += " (required)"
                self.parts.append(f"[FIELD: {text}]")
            self.in_label = False

    def handle_data(self, data) -> None:
        if self.skip or not data.strip():
            return
        if self.capture in {"heading", "button", "link"}:
            self.buf.append(data)
        elif self.in_label:
            self.label.append(data)
        else:
            self.parts.append(data)

    def _flush(self, title: str) -> None:
        if self.parts or self.chunks:
            self.chunks.append((self.title, self.parts))
        self.title = title
        self.parts = []

    def close_doc(self) -> list[tuple[str, list[str]]]:
        if self.parts or not self.chunks:
            self.chunks.append((self.title, self.parts))
        return [(title, parts) for title, parts in self.chunks if title != "Top of page" or any(part.strip() for part in parts)]


def _parse_html(raw: str) -> tuple[list[Section], str]:
    parser = _PageParser()
    parser.feed(raw)
    chunks = parser.close_doc()
    return _sections(chunks, "Top of page")


def _parse_text(raw: str) -> tuple[list[Section], str]:
    lines = raw.splitlines()
    if any(re.match(r"#{1,3} ", line) for line in lines):
        chunks = []
        title = "Top of page"
        parts: list[str] = []
        for line in lines:
            match = re.match(r"#{1,3} (.+)", line)
            if match:
                if parts or chunks:
                    chunks.append((title, parts))
                title = match.group(1).strip()
                parts = []
            else:
                parts.append(line)
        chunks.append((title, parts))
        return _sections(chunks, "Top of page")
    numbered = [line for line in lines if re.match(r"\s*(\d+[.)]|Step \d+[:.])", line)]
    if numbered:
        chunks = []
        for line in lines:
            match = re.match(r"\s*(?:\d+[.)]|Step \d+[:.])\s*(.*)", line)
            if match:
                chunks.append((match.group(1).strip() or line.strip(), [line]))
        return _sections(chunks, "Text")
    paragraphs = [block.strip() for block in re.split(r"\n\s*\n", raw) if block.strip()]
    return _sections([(f"Paragraph {index}", [block]) for index, block in enumerate(paragraphs, start=1)], "Text")


def _parse_botscript(raw: str) -> tuple[list[Section], str]:
    import yaml
    data = yaml.safe_load(raw)
    chunks = []
    for node in data.get("nodes") or []:
        bits = [node.get("bot") or ""]
        for option in node.get("options") or []:
            bits.append(f"[BUTTON: {option}]")
        chunks.append((str(node.get("id")), bits))
    return _sections(chunks, data.get("title") or "Botscript")
