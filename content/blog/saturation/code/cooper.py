"""Timed solver: stream exam attempts and record when every text chunk arrived.

The clock starts when the request is sent (api) or at Claude Code's init event (cli), so it includes network latency, prompt processing and thinking. The model is not told the deadline, and one complete stream yields the answer sheet at every budget T: generation is causal, so the text that has arrived by T is exactly what a hard cut at T would have collected.

The default backend is the Claude Code CLI on the logged-in subscription; --backend api uses the Anthropic SDK and needs an API key, but gives the cleaner clock (no CLI in between) and fast mode. campaign.py drives many runs of many configurations; this script runs one configuration.

    .venv/bin/python cooper.py --model claude-opus-5-5 --effort low --runs 1
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import anthropic

import exam

SYSTEM = """You are sitting the Finnish matriculation examination in mathematics, advanced syllabus (pitkä matematiikka), under time pressure. The complete exam is in the user message, transcribed from the official exam into Markdown with LaTeX math.

Your answer sheet is collected at a deadline you are not told. Whatever you have written by then is graded; nothing after it is.

- The answers are graded by the official Finnish grading guidelines (hyvän vastauksen piirteet). Each question is worth 0–12 points, and a solution needs the necessary calculations or other sufficient justification and a final result, unless the question says that an answer alone is enough. Only your written answers are graded, not your internal reasoning.
- The exam's instructions on how many questions to answer do not apply here: answer all {n} questions, in the order of the exam. Every answer is graded.
- Begin every answer with a line containing only `## N`, where N is the question number. Write nothing before the first such line.
- You have no calculator, software or other tools.
- Write your answers in {language}, as plain Markdown with LaTeX math.{extra}"""

LANGUAGE = {"fi": "Finnish, the language of the exam", "en": "English"}
# After the exam's own closing reminder to check that the number of answers follows its instructions.
CLOSING = "\n\n---\n\nEnd of the exam. Answer all {n} questions, in the order of the exam."
NO_THINKING = '{"alwaysThinkingEnabled": false}'
# Each model's maximum output (Anthropic's model overview; Claude Code 2.1.281 has the same upper limits), so that thinking never runs into a cap below it: a Sonnet 5 run at high effort used 63,138 tokens.
MAX_OUTPUT = {"claude-haiku-4-5": 64000, "claude-sonnet-5": 128000, "claude-opus-5-5": 128000, "claude-fable-5-1": 128000}
PROMPTS = {
    "default": "",
    "speed": "\n- Speed matters more than anything else. Start writing your first answer at once, without working out the whole exam first: solve each question while you write its answer. Keep every answer as short as a full-marks answer can be.",
}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", default="2025")
    p.add_argument("--model", default="claude-opus-5-5")
    p.add_argument("--effort", choices=["low", "medium", "high", "xhigh", "max"])
    p.add_argument("--no-thinking", action="store_true",
                   help="switch thinking off (works for Haiku 4.5 and Sonnet 5; Opus 5.5 and Fable 5.1 cannot)")
    p.add_argument("--fast", action="store_true", help="fast mode (research preview, api backend, needs access)")
    p.add_argument("--lang", choices=list(LANGUAGE), default="fi")
    p.add_argument("--prompt", choices=list(PROMPTS), default="default", help="prompt variant")
    p.add_argument("--runs", type=int, default=10)
    p.add_argument("--tmax", type=float, default=720, help="stop reading after this many seconds (the Cooper limit)")
    p.add_argument("--max-tokens", type=int, help="default: the model's maximum output")
    p.add_argument("--backend", choices=["cli", "api"], default="cli",
                   help="cli: Claude Code on the logged-in subscription; api: Anthropic SDK, needs an API key")
    p.add_argument("--tag")
    return p


def tag_of(args) -> str:
    return args.tag or "_".join(filter(None, [
        args.model, args.effort or "e-default", "nothink" if args.no_thinking else None,
        None if args.prompt == "default" else args.prompt, args.lang,
        "fast" if args.fast else None, args.backend,
    ]))


def request(args) -> dict:
    n = sum(len(qs) for qs in exam.meta(args.year)["sections"].values())
    req = {
        "model": args.model,
        "max_tokens": args.max_tokens or MAX_OUTPUT[args.model],
        "system": SYSTEM.format(n=n, language=LANGUAGE[args.lang], extra=PROMPTS[args.prompt]),
        "messages": [{"role": "user", "content": exam.exam_text(args.year).rstrip() + CLOSING.format(n=n)}],
    }
    if args.effort:
        req["output_config"] = {"effort": args.effort}
    if args.no_thinking:
        req["thinking"] = {"type": "disabled"}
    if args.fast:
        req |= {"speed": "fast", "betas": ["fast-mode-2026-02-01"]}
    return req


def record(rec: dict, ev: dict, t: float):
    """Fold one raw Messages-API stream event (as a dict) into the run record."""
    kind = ev.get("type")
    if kind == "message_start":
        rec["t_message_start"], rec["message_id"] = t, ev["message"]["id"]
    elif kind == "content_block_start":
        rec["blocks"].append([ev["content_block"]["type"], t, None])
    elif kind == "content_block_stop":
        rec["blocks"][-1][2] = t
    elif kind == "content_block_delta" and ev["delta"]["type"] == "text_delta":
        rec["chunks"].append([t, ev["delta"]["text"]])
    elif kind == "message_delta":
        rec["stop_reason"], rec["usage"] = ev["delta"]["stop_reason"], ev["usage"]


def new_record() -> dict:
    return {"chunks": [], "blocks": [], "cut": False,
            "started_at": dt.datetime.now(dt.timezone.utc).isoformat()}


def finish(rec: dict, t_end: float) -> dict:
    rec["t_end"] = t_end
    rec["t_first_text"] = rec["chunks"][0][0] if rec["chunks"] else None
    if not rec["cut"] and rec.get("stop_reason") not in ("end_turn", "max_tokens"):
        raise RuntimeError(f"run ended without an answer: stop_reason={rec.get('stop_reason')}, "
                           f"cli={rec.get('cli_result', {}).get('result')!r:.300}")
    return rec


def attempt_api(client: anthropic.Anthropic, req: dict, cut: float) -> dict:
    messages = client.beta.messages if "betas" in req else client.messages
    t = time.perf_counter()
    client.models.retrieve(req["model"])  # warm the pooled connection so no run pays the TLS handshake
    rec = new_record() | {"backend": "api", "rtt_warmup": time.perf_counter() - t}
    t0 = time.perf_counter()
    with messages.stream(**req) as stream:
        for ev in stream:
            t = time.perf_counter() - t0
            record(rec, ev.model_dump(), t)
            if t > cut:
                rec["cut"] = True
                break
    return finish(rec, time.perf_counter() - t0)


def claude_bin() -> str:
    found = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    if found:
        return found
    bundled = sorted(Path.home().glob(".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"))
    if not bundled:
        raise SystemExit("claude CLI not found; set CLAUDE_BIN")
    return str(bundled[-1])


def cli_cmd(system: str, model: str, effort: str | None, *extra: str, no_thinking: bool = False) -> list[str]:
    """Claude Code in print mode with its own system prompt replaced, no tools, and --safe-mode and
    --setting-sources "" keeping CLAUDE.md, hooks, MCP servers, skills, plugins and settings out."""
    cmd = [claude_bin(), "-p", "--system-prompt", system, "--tools", "", "--model", model,
           "--no-session-persistence", "--safe-mode", "--strict-mcp-config", "--setting-sources", "", *extra]
    if no_thinking:
        cmd += ["--settings", NO_THINKING]
    return cmd + ["--effort", effort] if effort else cmd


def run_cli(cmd: list[str], **kw):
    """Run the CLI in a fresh empty directory: Claude Code tells the model its working directory."""
    with tempfile.TemporaryDirectory() as cwd:
        return subprocess.run(cmd, cwd=cwd, **kw)


def attempt_cli(req: dict, cut: float) -> dict:
    """The same request through Claude Code, on the logged-in subscription. Times are measured
    from the CLI's init event, i.e. after its start-up, which is recorded as t_startup."""
    cmd = cli_cmd(req["system"], req["model"], req.get("output_config", {}).get("effort"),
                  "--output-format", "stream-json", "--include-partial-messages", "--verbose",
                  no_thinking="thinking" in req)
    env = os.environ | {"CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(req["max_tokens"])}
    rec = new_record() | {"backend": "cli"}
    with tempfile.TemporaryDirectory() as cwd:
        t_spawn = time.perf_counter()
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, bufsize=1, cwd=cwd, env=env)
        proc.stdin.write(req["messages"][0]["content"])
        proc.stdin.close()
        t0 = None
        for line in proc.stdout:
            now = time.perf_counter()
            msg = json.loads(line)
            if t0 is None:
                if msg.get("type") == "system" and msg.get("subtype") == "init":
                    t0 = now
                    rec |= {"t_startup": now - t_spawn, "cli_init": msg}
                continue
            t = now - t0
            if msg.get("type") == "stream_event":
                record(rec, msg["event"], t)
            elif msg.get("type") == "system" and msg.get("subtype") != "thinking_tokens":
                rec.setdefault("cli_system", []).append([t, msg.get("subtype")])  # e.g. a retry inside the CLI
            elif msg.get("type") == "result":
                rec["cli_result"] = {k: msg.get(k) for k in
                                     ("subtype", "is_error", "duration_ms", "duration_api_ms", "num_turns",
                                      "total_cost_usd", "usage", "modelUsage", "result")}
            if t > cut:
                rec["cut"] = True
                proc.kill()
                break
        proc.wait()
        stderr = proc.stderr.read()
    if t0 is None:
        raise RuntimeError(f"claude CLI exited with {proc.returncode} before streaming: {stderr[-300:]}")
    if rec.get("cli_result", {}).get("is_error"):
        raise RuntimeError(f"claude CLI error: {rec['cli_result'].get('result')!r:.300}")
    return finish(rec, time.perf_counter() - t0)


def attempt(args, req: dict, client=None) -> dict:
    return attempt_api(client, req, args.tmax) if args.backend == "api" else attempt_cli(req, args.tmax)


def run_dir(args) -> Path:
    return exam.ROOT / "runs" / args.year / tag_of(args)


def prompt_sha(req: dict) -> str:
    return hashlib.sha256((req["system"] + req["messages"][0]["content"]).encode()).hexdigest()[:12]


def save(args, req: dict, rec: dict, index: int, **meta) -> Path:
    out = run_dir(args)
    out.mkdir(parents=True, exist_ok=True)
    config = {k: v for k, v in vars(args).items() if k not in ("runs", "tag")}
    rec |= {"config": config, "tag": tag_of(args), "prompt_sha": prompt_sha(req), "system": req["system"],
            "max_tokens": req["max_tokens"], **meta}
    path = out / f"run{index:02d}.json"
    path.write_text(json.dumps(rec, ensure_ascii=False))
    return path


def summary(rec: dict) -> str:
    n = sum(len(c[1]) for c in rec["chunks"])
    think = (rec.get("usage") or {}).get("output_tokens_details") or {}
    return (f"first text {rec['t_first_text'] or float('nan'):.1f}s, end {rec['t_end']:.1f}s, {n} chars, "
            f"thinking tokens {think.get('thinking_tokens')}, stop {rec.get('stop_reason')}, cut {rec['cut']}")


def main():
    args = parser().parse_args()
    if args.backend == "cli" and args.fast:
        raise SystemExit("--fast needs --backend api")
    req = request(args)
    # Retries would silently add backoff time to the measured clock; a failed run is redone instead.
    client = anthropic.Anthropic(max_retries=0) if args.backend == "api" else None
    done = len(list(run_dir(args).glob("run*.json")))
    failures = 0
    while done < args.runs:
        try:
            rec = attempt(args, req, client)
        except (anthropic.APIStatusError, anthropic.APIConnectionError, RuntimeError) as e:
            failures += 1
            print(f"run {done}: {type(e).__name__}: {e}")
            if failures > 3 * args.runs:
                raise
            time.sleep(10)
            continue
        save(args, req, rec, done)
        print(f"run {done}: {summary(rec)}")
        done += 1


if __name__ == "__main__":
    main()
