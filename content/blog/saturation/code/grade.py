"""Grade the recorded answer sheets at each time budget T with the official rubric.

Grading is per question: the grader sees one question's rubric and one answer, and nothing about the model, the configuration or the time budget. Each (question, answer text) pair is graded once and cached, so an answer finished by T = 60 s carries the same grade at every later T; only answers cut off mid-writing are graded again. Two scores per budget: all 13 answers (max 156), and the best 5/3/2 per part (max 120), what a candidate choosing afterwards would get.

    .venv/bin/python grade.py --year 2025 --dry     # count grading calls first
    .venv/bin/python grade.py --year 2025
"""
import argparse
import bisect
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor

import anthropic
import numpy as np

import exam
from cooper import cli_cmd, run_cli

# Log-spaced: ratio 1.21 between budgets; the first 20 reach ~190 s, the rest continue to the 12-minute Cooper limit.
GRID = [float(f"{t:.3g}") for t in np.geomspace(5, 720, 27)]
VERSION = "g1"

SYSTEM = """You are an experienced grader (sensori) of the Finnish matriculation examination in mathematics, advanced syllabus. You grade one candidate answer to one question, strictly by the official grading guidelines (hyvän vastauksen piirteet) below, as an official grader would.

- Apply the question's scoring rows and the general rules and deductions exactly as written. Where the guidelines do not cover a correct solution method, award points in the spirit of the rows: an equivalent correct method earns equivalent points.
- The answer may stop abruptly, even mid-sentence or mid-formula. Grade only what is written; give no credit for steps that were not written.
- The candidate had no calculator or software. Rows satisfied by documented software use are satisfied only by equivalent work shown by hand.
- The language of the answer (Finnish or English) does not affect the grade.
- Report every scoring row you applied with the points awarded, every deduction, and the total as an integer from 0 to 12.

# General grading guidelines

{general}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "rows": {"type": "array", "items": {
            "type": "object",
            "properties": {"row": {"type": "string"}, "awarded": {"type": "number"}, "comment": {"type": "string"}},
            "required": ["row", "awarded", "comment"], "additionalProperties": False,
        }},
        "deductions": {"type": "array", "items": {
            "type": "object",
            "properties": {"reason": {"type": "string"}, "points": {"type": "number"}},
            "required": ["reason", "points"], "additionalProperties": False,
        }},
        "points": {"type": "integer"},
    },
    "required": ["rows", "deductions", "points"], "additionalProperties": False,
}

RUN_FIELDS = ("started_at", "t_startup", "t_message_start", "t_first_text", "t_end", "stop_reason", "cut", "usage", "blocks", "cli_system", "round", "wall_start", "wall_end", "parallel")


def sheet_at(times: list[float], texts: list[str], T: float) -> str:
    return "".join(texts[: bisect.bisect_right(times, T)])


def split_times(run: dict) -> dict[int, list[float]]:
    """[start, finish] of each answer: arrival of its header, and of the next header (or stream end)."""
    full = "".join(c[1] for c in run["chunks"])
    ends = [0]
    for c in run["chunks"]:
        ends.append(ends[-1] + len(c[1]))
    at = lambda pos: run["chunks"][bisect.bisect_right(ends, pos) - 1][0]
    heads = list(exam.ANSWER_HEADER.finditer(full))
    out = {}
    for i, h in enumerate(heads):
        out.setdefault(int(h.group(1)), [at(h.start()), at(heads[i + 1].start()) if i + 1 < len(heads) else run["t_end"]])
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", default="2025")
    p.add_argument("--tags", nargs="*", help="default: every tag under runs/<year>")
    p.add_argument("--model", default="claude-opus-5-5")
    p.add_argument("--effort", default="xhigh")
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--backend", choices=["cli", "api"], default="cli")
    p.add_argument("--dry", action="store_true")
    args = p.parse_args()

    general, per_q = exam.rubric(args.year)
    m = exam.meta(args.year)
    system = SYSTEM.format(general=general)
    runs = [
        json.loads(f.read_text())
        for d in sorted((exam.ROOT / "runs" / args.year).iterdir()) if not args.tags or d.name in args.tags
        for f in sorted(d.glob("run*.json"))
    ]

    key = lambda q, text: hashlib.sha256(f"{VERSION}|{args.model}|{args.effort}|{q}|{text}".encode()).hexdigest()
    cache_file = exam.ROOT / "grades" / args.year / "cache.jsonl"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache = {}
    if cache_file.exists():
        for line in cache_file.read_text().splitlines():
            g = json.loads(line)
            cache[g["key"]] = g

    sheets = {}  # (run index, T) -> {question: answer text}
    todo = {}
    for i, run in enumerate(runs):
        times, texts = [c[0] for c in run["chunks"]], [c[1] for c in run["chunks"]]
        for T in GRID + ["final"]:
            answers = exam.first_answers(exam.segment("".join(texts) if T == "final" else sheet_at(times, texts, T)))
            sheets[i, T] = answers
            for q, text in answers.items():
                k = key(q, text)
                if k not in cache and q in per_q:
                    todo[k] = (q, text)
    print(f"{len(runs)} runs, {len(todo)} answers to grade ({len(cache)} cached)", flush=True)
    if args.dry:
        return

    client = anthropic.Anthropic(max_retries=6) if args.backend == "api" else None

    def ask_api(user: str) -> dict:
        msg = client.messages.create(
            model=args.model, max_tokens=32000, system=system,
            output_config={"effort": args.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": user}],
        )
        if msg.stop_reason != "end_turn":
            raise RuntimeError(f"grader stopped with {msg.stop_reason}")
        return json.loads(next(b.text for b in msg.content if b.type == "text"))

    def ask_cli(user: str) -> dict:
        cmd = cli_cmd(system, args.model, args.effort, "--output-format", "json", "--json-schema", json.dumps(SCHEMA))
        proc = run_cli(cmd, input=user, capture_output=True, text=True)
        if proc.returncode:
            raise RuntimeError(f"grader CLI exited with {proc.returncode}: {(proc.stdout or proc.stderr)[-300:]!r}")
        msg = json.loads(proc.stdout)
        if msg.get("is_error"):
            raise RuntimeError(f"grader CLI error: {msg.get('result')!r:.300}")
        return msg.get("structured_output") or json.loads(msg["result"])

    def grade(item):
        k, (q, text) = item
        user = f"# Question and its grading guidelines\n\n{per_q[q]}\n\n# Candidate answer\n\n{text}"
        for attempt in range(4):
            try:
                g = ask_api(user) if client else ask_cli(user)
                if isinstance(g.get("points"), int) and 0 <= g["points"] <= m["points_per_question"]:
                    return {"key": k, "q": q, "answer": text, **g, "model": args.model, "effort": args.effort}
                err = f"points out of range: {g.get('points')!r}"
            except (json.JSONDecodeError, KeyError, RuntimeError) as e:
                err = f"{type(e).__name__}: {e}"
            print(f"grading q{q} failed (attempt {attempt + 1}): {err:.300}", flush=True)
            time.sleep(20 * (attempt + 1))
        raise RuntimeError(f"grading question {q} failed four times")

    done = 0
    with ThreadPoolExecutor(args.workers) as pool, cache_file.open("a") as f:
        for g in pool.map(grade, todo.items()):
            cache[g["key"]] = g
            f.write(json.dumps(g, ensure_ascii=False) + "\n")
            f.flush()
            done += 1
            if done % 50 == 0:
                print(f"graded {done}/{len(todo)}", flush=True)

    results = {}
    for i, run in enumerate(runs):
        at = {}
        for T in GRID + ["final"]:
            pts = {q: cache[key(q, text)]["points"] for q, text in sheets[i, T].items() if q in per_q}
            at[str(T)] = {"score": sum(pts.values()), "score120": exam.best_quota(pts, m), "points": pts}
        results.setdefault(run["tag"], []).append(
            {k: run.get(k) for k in RUN_FIELDS} | {
                "chars": sum(len(c[1]) for c in run["chunks"]),
                # Longest silence after the first word: a second thinking phase would show up here.
                "max_gap": float(np.diff([c[0] for c in run["chunks"]]).max(initial=0)),
                "lengths": {q: len(text) for q, text in sheets[i, "final"].items()},
                "model_usage": (run.get("cli_result") or {}).get("modelUsage"),
                "splits": split_times(run), "order": list(sheets[i, "final"]), "at": at,
            })
    out = exam.ROOT / "results" / args.year
    out.mkdir(parents=True, exist_ok=True)
    for tag, rs in results.items():
        config = next(r["config"] for r in runs if r["tag"] == tag)
        (out / f"{tag}.json").write_text(json.dumps(
            {"tag": tag, "config": config, "grid": GRID, "runs": rs}, ensure_ascii=False, indent=1))
        finals = [r["at"]["final"]["score"] for r in rs]
        print(f"{tag}: final scores (of 156) {finals}", flush=True)


if __name__ == "__main__":
    main()
