"""Run the whole matrix of configurations.

Round 1 (one run of every configuration) goes one at a time, as a check and a solo baseline; the later rounds follow in a shuffled order, --parallel runs at a time, so that drift over the evening does not line up with any one configuration. Every run stores its wall-clock interval, from which the analysis finds how many runs overlapped it. Resumable: finished runs are skipped. It stops after three consecutive failures, which usually means a usage limit.

    .venv/bin/python campaign.py --year 2025 --rounds 1                # round 1 only
    .venv/bin/python campaign.py --year 2025                           # everything left
    .venv/bin/python campaign.py --year 2026 --groups fable            # one group
"""
import argparse
import json
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import cooper

EFFORTS = ["low", "medium", "high"]
GROUPS = {
    # Thinking can be switched off: Haiku 4.5, which has no effort levels, and Sonnet 5 at every effort.
    "haiku": [("claude-haiku-4-5", None, False), ("claude-haiku-4-5", None, True)],
    "sonnet": [("claude-sonnet-5", e, off) for off in (False, True) for e in EFFORTS],
    # Thinking cannot be switched off: Opus 5.5 ignores the setting, Fable 5.1 always thinks.
    "opus": [("claude-opus-5-5", e, False) for e in EFFORTS],
    "fable": [("claude-fable-5-1", e, False) for e in EFFORTS],
    # Pilot only: the speed prompt, and whether the thinking-off setting reaches Opus 5.5.
    "probe": [("claude-opus-5-5", "low", True), ("claude-opus-5-5", "low", False, "speed"),
              ("claude-sonnet-5", "low", False, "speed")],
}


def config_args(year: str, model: str, effort: str | None, no_thinking: bool, prompt: str = "default"):
    return cooper.parser().parse_args(
        ["--year", year, "--model", model, "--prompt", prompt] + (["--effort", effort] if effort else [])
        + (["--no-thinking"] if no_thinking else []))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", default="2025")
    p.add_argument("--groups", nargs="+", default=["haiku", "sonnet", "opus", "fable"], choices=list(GROUPS))
    p.add_argument("--runs", type=int, default=10)
    p.add_argument("--rounds", type=int, help="run only up to this round")
    p.add_argument("--parallel", type=int, default=9)
    p.add_argument("--seed", type=int, help="shuffle seed (default: the year)")
    args = p.parse_args()

    configs = [config_args(args.year, *c) for g in args.groups for c in GROUPS[g]]
    for c in configs:
        req = cooper.request(c)
        made = [json.loads(f.read_text()) for f in cooper.run_dir(c).glob("run*.json")]
        stale = [r for r in made if (r["prompt_sha"], r.get("max_tokens")) != (cooper.prompt_sha(req), req["max_tokens"])]
        if stale:
            raise SystemExit(f"{cooper.tag_of(c)}: {len(stale)} runs were made with another prompt or token limit; "
                             "move them away first")
    rng = random.Random(args.seed if args.seed is not None else int(args.year))
    rounds = []
    for r in range(min(args.runs, args.rounds or args.runs)):
        order = configs[:]
        rng.shuffle(order)
        rounds.append([(c, r) for c in order if not (cooper.run_dir(c) / f"run{r:02d}.json").exists()])

    lock = threading.Lock()
    state = {"consecutive_failures": 0, "stop": False}

    def job(item):
        c, r = item
        req = cooper.request(c)
        for attempt in range(3):
            if state["stop"]:
                return
            wall_start = time.time()
            try:
                rec = cooper.attempt(c, req)
            except RuntimeError as e:
                with lock:
                    state["consecutive_failures"] += 1
                    state["stop"] = state["consecutive_failures"] >= 3
                print(f"FAIL {cooper.tag_of(c)} run{r:02d} (attempt {attempt + 1}): {e}", flush=True)
                time.sleep(30)
                continue
            with lock:
                state["consecutive_failures"] = 0
            cooper.save(c, req, rec, r, round=r + 1, wall_start=wall_start, wall_end=time.time(),
                        parallel=1 if r == 0 else args.parallel)
            print(f"{time.strftime('%H:%M:%S')} {cooper.tag_of(c)} run{r:02d}: {cooper.summary(rec)}", flush=True)
            return

    for r, items in enumerate(rounds):
        if state["stop"]:
            break
        if r == 0:
            for item in items:
                job(item)
            continue
        with ThreadPoolExecutor(args.parallel) as pool:
            list(pool.map(job, [it for rest in rounds[r:] for it in rest]))
        break
    if state["stop"]:
        raise SystemExit("stopped after three consecutive failures (usage limit?); rerun to resume")
    print("campaign complete", flush=True)


if __name__ == "__main__":
    main()
