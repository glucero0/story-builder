from __future__ import annotations

import html
import re

from story_builder.assemble import SourceFile

FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n(?:---|\.\.\.)\s*\n", re.DOTALL)
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
FENCE_RE = re.compile(r"```[\w+-]*\n?(.*?)```", re.DOTALL)
TILDE_FENCE_RE = re.compile(r"~~~[\w+-]*\n?(.*?)~~~", re.DOTALL)
IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
REF_LINK_RE = re.compile(r"\[([^\]]+)\]\[[^\]]*\]")
REF_DEF_RE = re.compile(r"^\s*\[[^\]]+\]:\s+\S+.*$", re.MULTILINE)
FOOTNOTE_RE = re.compile(r"\[\^[^\]]+\]:?")
SETTEXT_RE = re.compile(r"^(.*?)\n[=-]{3,}\s*$", re.MULTILINE)
ATX_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
TRAILING_HASH_RE = re.compile(r"[ \t]+#+\s*$", re.MULTILINE)
BLOCKQUOTE_RE = re.compile(r"^\s{0,3}>\s?", re.MULTILINE)
HR_RE = re.compile(r"^\s{0,3}(?:[-*_]){3,}\s*$", re.MULTILINE)
LIST_RE = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+", re.MULTILINE)
TABLE_SEP_RE = re.compile(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$", re.MULTILINE)
BOLD_RE = re.compile(r"(\*\*\*|___|\*\*|__)(.*?)(\1)")
ITALIC_RE = re.compile(r"(?<!\w)([*_])([^*_]+)\1(?!\w)")
STRIKE_RE = re.compile(r"~~(.*?)~~")
INLINE_CODE_RE = re.compile(r"`([^`]+)`")
HTML_TAG_RE = re.compile(r"</?[^>]+>")
SPACE_RE = re.compile(r"[ \t]+")


def to_plain_text(text: str) -> str:
    """Strip Markdown, HTML, and blank lines, leaving readable prose."""
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = FRONTMATTER_RE.sub("", cleaned)
    cleaned = HTML_COMMENT_RE.sub("", cleaned)
    cleaned = FENCE_RE.sub(lambda match: match.group(1).strip(), cleaned)
    cleaned = TILDE_FENCE_RE.sub(lambda match: match.group(1).strip(), cleaned)
    cleaned = IMAGE_RE.sub("", cleaned)
    cleaned = LINK_RE.sub(r"\1", cleaned)
    cleaned = REF_LINK_RE.sub(r"\1", cleaned)
    cleaned = REF_DEF_RE.sub("", cleaned)
    cleaned = FOOTNOTE_RE.sub("", cleaned)
    cleaned = SETTEXT_RE.sub(r"\1", cleaned)
    cleaned = ATX_HEADER_RE.sub("", cleaned)
    cleaned = TRAILING_HASH_RE.sub("", cleaned)
    cleaned = BLOCKQUOTE_RE.sub("", cleaned)
    cleaned = HR_RE.sub("", cleaned)
    cleaned = TABLE_SEP_RE.sub("", cleaned)
    cleaned = re.sub(r"^\s*\|", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.replace("|", " ")
    cleaned = LIST_RE.sub("", cleaned)
    cleaned = BOLD_RE.sub(r"\2", cleaned)
    cleaned = STRIKE_RE.sub(r"\1", cleaned)
    cleaned = ITALIC_RE.sub(r"\2", cleaned)
    cleaned = INLINE_CODE_RE.sub(r"\1", cleaned)
    cleaned = HTML_TAG_RE.sub("", cleaned)
    cleaned = html.unescape(cleaned)

    lines = [SPACE_RE.sub(" ", line).strip() for line in cleaned.split("\n")]
    lines = [line for line in lines if line]
    return " ".join(lines).strip()


def prepared_sources(files: list[SourceFile], strip_markdown: bool) -> list[SourceFile]:
    if not strip_markdown:
        return list(files)
    return [
        SourceFile(path=source.path, name=source.name, text=to_plain_text(source.text))
        for source in files
    ]
