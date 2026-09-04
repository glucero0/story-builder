from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceFile:
    path: str
    name: str
    text: str


@dataclass
class Arrangement:
    order: list[int]
    paragraphs: list[list[int]]
    notes: str = ""


def join_chunks(chunks: list[str]) -> str:
    """Join original fragments with boundary whitespace only. Words stay intact."""
    pieces: list[str] = []
    for chunk in chunks:
        piece = chunk.strip("\n")
        if piece:
            pieces.append(piece)

    if not pieces:
        return ""

    out = pieces[0]
    for piece in pieces[1:]:
        if out and not out[-1].isspace():
            out += " "
        out += piece.lstrip(" ")
    return out.strip()


def assemble(files: list[SourceFile], plan: Arrangement) -> str:
    by_id = {index: source for index, source in enumerate(files)}
    paragraphs: list[str] = []
    for group in plan.paragraphs:
        chunks = [by_id[file_id].text for file_id in group if file_id in by_id]
        paragraph = join_chunks(chunks)
        if paragraph:
            paragraphs.append(paragraph)
    return "\n\n".join(paragraphs)


def complete_order(order: list[int], file_count: int) -> list[int]:
    seen: list[int] = []
    used: set[int] = set()
    for file_id in order:
        if 0 <= file_id < file_count and file_id not in used:
            seen.append(file_id)
            used.add(file_id)
    for file_id in range(file_count):
        if file_id not in used:
            seen.append(file_id)
    return seen


def apply_paragraphs(order: list[int], groups: list[list[int]], file_count: int, notes: str = "") -> Arrangement:
    """`order` is the reading sequence. Paragraph groups only join neighbors in that sequence."""
    order = complete_order(order, file_count)
    group_of: dict[int, int] = {}
    for group_index, group in enumerate(groups):
        for file_id in group:
            if 0 <= file_id < file_count and file_id not in group_of:
                group_of[file_id] = group_index

    paragraphs: list[list[int]] = []
    current: list[int] = []
    current_group: int | None = None
    for file_id in order:
        membership = group_of.get(file_id)
        if membership is None:
            membership = -1 - file_id
        if current and membership != current_group:
            paragraphs.append(current)
            current = []
        if not current:
            current_group = membership
        current.append(file_id)
    if current:
        paragraphs.append(current)
    return Arrangement(order=order, paragraphs=paragraphs, notes=notes)


def validate_plan(plan: Arrangement, file_count: int) -> Arrangement:
    return apply_paragraphs(plan.order, plan.paragraphs, file_count, plan.notes)
