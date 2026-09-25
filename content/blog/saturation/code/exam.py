"""Exam and rubric loading, answer-sheet segmentation, and section quotas."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
QUESTION = re.compile(r"^## (\d+)\. ", re.M)
# The newline is required: at a cut, "## 1" may be the first half of "## 10".
ANSWER_HEADER = re.compile(r"^## (\d{1,2})[ \t]*\n", re.M)
PARTIAL_HEADER = re.compile(r"(?:^|\n)#[^\n]*\Z")


def meta(year: str) -> dict:
    return json.loads((ROOT / year / "meta.json").read_text())


def exam_text(year: str) -> str:
    return (ROOT / year / "exam.md").read_text()


def split(md: str) -> tuple[str, dict[int, str]]:
    """Preamble before the first question, and each question's section (up to the next '#'/'##' heading)."""
    heads = list(QUESTION.finditer(md))
    preamble = md[: heads[0].start()] if heads else md
    out = {}
    for h in heads:
        nxt = re.compile(r"^#{1,2} ", re.M).search(md, h.end())
        out[int(h.group(1))] = md[h.start(): nxt.start() if nxt else len(md)].strip()
    return preamble.strip(), out


def rubric(year: str) -> tuple[str, dict[int, str]]:
    general, per_q = split((ROOT / year / "rubric.md").read_text())
    return general.split("\n# ")[0].strip(), per_q


def segment(sheet: str) -> list[tuple[int, str]]:
    """Non-empty answers in written order, as (question, text). Text before the first header is dropped."""
    sheet = PARTIAL_HEADER.sub("", sheet)
    heads = list(ANSWER_HEADER.finditer(sheet))
    out = []
    for i, h in enumerate(heads):
        text = sheet[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(sheet)].strip()
        if text:
            out.append((int(h.group(1)), text))
    return out


def first_answers(answers: list[tuple[int, str]]) -> dict[int, str]:
    """One answer per question: the first one written, if a header was repeated."""
    out = {}
    for q, text in answers:
        out.setdefault(q, text)
    return out


def best_quota(points: dict[int, int], m: dict) -> int:
    """The exam score a candidate choosing afterwards would get: the best `quota` answers of each part."""
    return sum(sum(sorted((points.get(q, 0) for q in qs), reverse=True)[: m["quota"][s]])
               for s, qs in m["sections"].items())
