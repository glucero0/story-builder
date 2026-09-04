from __future__ import annotations

import json
import random
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from story_builder.assemble import Arrangement, SourceFile, apply_paragraphs

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_CHARS_PER_FILE = 6000

SYSTEM_PROMPT = """You are sequencing scrambled fragments of one document.

The fragments are about the same subject, but the order you receive them in is RANDOM.
Do not keep the listing order. Infer the true reading order from meaning: chronology,
cause and effect, setup then payoff, speaker turns, and narrative flow.

Also group consecutive fragments into paragraphs when they belong together.
Start a new paragraph on a shift in scene, time, speaker, or topic.

Strict rules:
- Do not rewrite, paraphrase, summarize, or correct the source text.
- Do not invent missing sentences.
- Identify fragments only by their labels (A, B, C, ...). Never use filenames as ids.
- "order" is the full reading sequence and is the field that matters most.
- Every label appears exactly once in "order".
- "paragraphs" groups labels that already appear in "order"; it must follow that same sequence.

Return JSON only:
{
  "opening": "C",
  "order": ["C", "A", "B"],
  "paragraphs": [["C", "A"], ["B"]],
  "notes": "one short sentence explaining why this is the reading order"
}
"""

FILE_LABEL_RE = re.compile(r"(?:fragment|file|id)\s*[-_:]?\s*([A-Za-z]+|\d+)", re.IGNORECASE)
BARE_LABEL_RE = re.compile(r"^[A-Za-z]+$")
LEADING_ID_RE = re.compile(r"^\s*(\d+)\b")


@dataclass
class IdMap:
    files: list[SourceFile]
    label_to_index: dict[str, int]
    slot_to_index: list[int]


def _alpha_label(index: int) -> str:
    n = index + 1
    chars: list[str] = []
    while n:
        n, rem = divmod(n - 1, 26)
        chars.append(chr(65 + rem))
    return "".join(reversed(chars))


def scramble_files(files: list[SourceFile]) -> tuple[list[tuple[str, SourceFile]], IdMap]:
    slots = list(range(len(files)))
    random.shuffle(slots)
    labeled: list[tuple[str, SourceFile]] = []
    label_to_index: dict[str, int] = {}
    for slot, original_index in enumerate(slots):
        label = _alpha_label(slot)
        labeled.append((label, files[original_index]))
        label_to_index[label] = original_index
        label_to_index[label.lower()] = original_index
    return labeled, IdMap(files=files, label_to_index=label_to_index, slot_to_index=slots)


def _excerpt(text: str) -> str:
    if len(text) <= MAX_CHARS_PER_FILE:
        return text
    head = MAX_CHARS_PER_FILE - 1200
    tail = 1000
    return f"{text[:head]}\n\n[...middle omitted for ordering...]\n\n{text[-tail:]}"


def build_user_prompt(labeled: list[tuple[str, SourceFile]]) -> str:
    blocks = []
    for label, source in labeled:
        blocks.append(
            f"--- FRAGMENT {label} ---\n{_excerpt(source.text)}\n--- END FRAGMENT {label} ---"
        )
    return (
        "These fragments are scrambled. The sequence below is NOT the story order. "
        "Return the true reading order using the fragment labels.\n\n"
        + "\n\n".join(blocks)
    )


def _extract_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("The model did not return usable JSON for the file order.") from exc
    if not isinstance(data, dict):
        raise ValueError("Model did not return a JSON object.")
    return data


def arrange_files(api_key: str, model: str, files: list[SourceFile]) -> Arrangement:
    if not api_key.strip():
        raise ValueError("Add your OpenRouter API key first.")
    if len(files) < 2:
        raise ValueError("Drop at least two files so there is something to order.")

    labeled, id_map = scramble_files(files)
    prompt = build_user_prompt(labeled)

    try:
        data = _complete(api_key, model, prompt, use_json_format=True)
    except RuntimeError as exc:
        message = str(exc).lower()
        if "response_format" in message or "json_object" in message:
            data = _complete(api_key, model, prompt, use_json_format=False)
        else:
            raise

    order = _parse_id_list(data.get("order"), id_map)
    opening = coerce_file_id(data.get("opening"), id_map)
    if not order and opening is not None:
        order = [opening]

    groups = _parse_paragraph_groups(data.get("paragraphs"), id_map)
    notes = str(data.get("notes") or "").strip()
    return apply_paragraphs(order, groups, len(files), notes)


def coerce_file_id(value: Any, id_map: IdMap) -> int | None:
    """Map a model label, prompt slot, or filename back to the original file index."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        if 0 <= value < len(id_map.slot_to_index):
            return id_map.slot_to_index[value]
        return None
    if isinstance(value, float) and value.is_integer():
        return coerce_file_id(int(value), id_map)
    if isinstance(value, dict):
        for key in ("id", "file_id", "index", "file", "label", "fragment"):
            if key in value:
                parsed = coerce_file_id(value[key], id_map)
                if parsed is not None:
                    return parsed
        return None
    if not isinstance(value, str):
        return None

    text = value.strip().strip("\"'")
    if not text:
        return None

    if text.isdigit():
        return coerce_file_id(int(text), id_map)

    if BARE_LABEL_RE.match(text) and text.upper() in id_map.label_to_index:
        return id_map.label_to_index[text.upper()]

    match = FILE_LABEL_RE.search(text)
    if match:
        parsed = coerce_file_id(match.group(1), id_map)
        if parsed is not None:
            return parsed

    leading = LEADING_ID_RE.match(text)
    if leading:
        parsed = coerce_file_id(int(leading.group(1)), id_map)
        if parsed is not None:
            return parsed

    lowered = text.lower()
    for index, source in enumerate(id_map.files):
        names = {source.name.lower(), source.path.lower(), source.name.rsplit(".", 1)[0].lower()}
        if lowered in names or lowered.replace("\\", "/").endswith("/" + source.name.lower()):
            return index
    return None


def _parse_id_list(values: Any, id_map: IdMap) -> list[int]:
    if not isinstance(values, list):
        return []
    order: list[int] = []
    seen: set[int] = set()
    for item in values:
        if isinstance(item, list):
            for file_id in _parse_id_list(item, id_map):
                if file_id not in seen:
                    seen.add(file_id)
                    order.append(file_id)
            continue
        file_id = coerce_file_id(item, id_map)
        if file_id is None or file_id in seen:
            continue
        seen.add(file_id)
        order.append(file_id)
    return order


def _parse_paragraph_groups(values: Any, id_map: IdMap) -> list[list[int]]:
    if not isinstance(values, list) or not values:
        return []
    if not isinstance(values[0], list):
        parsed = _parse_id_list(values, id_map)
        return [[file_id] for file_id in parsed]
    groups: list[list[int]] = []
    seen: set[int] = set()
    for group in values:
        unique = [file_id for file_id in _parse_id_list(group, id_map) if file_id not in seen]
        if unique:
            seen.update(unique)
            groups.append(unique)
    return groups


def _complete(api_key: str, model: str, prompt: str, use_json_format: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    if use_json_format:
        payload["response_format"] = {"type": "json_object"}

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        OPENROUTER_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://local.story-builder",
            "X-Title": "Story Builder",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(_friendly_http_error(exc.code, detail)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach OpenRouter: {exc.reason}") from exc

    envelope = json.loads(raw)
    if envelope.get("error"):
        message = envelope["error"]
        if isinstance(message, dict):
            message = message.get("message") or str(message)
        raise RuntimeError(str(message))

    choices = envelope.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter returned no choices.")
    content = choices[0].get("message", {}).get("content") or ""
    return _extract_json(content)


def _friendly_http_error(status: int, detail: str) -> str:
    snippet = detail[:400].strip()
    if status == 401:
        return "OpenRouter rejected the API key. Check it and try again."
    if status == 402:
        return "OpenRouter says this account is out of credits."
    if status == 429:
        return "OpenRouter rate-limited the request. Wait a moment and try again."
    return f"OpenRouter HTTP {status}: {snippet or 'request failed'}"
