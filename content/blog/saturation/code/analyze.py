"""Statistics and figures from graded results.

Per configuration: mean ± SD over runs of the score at every budget T (all answers, max 156 in 2025, and the best 5/3/2, max 120), the timing phases, the structure of the answer stream, and saturation times read off the mean curve by interpolating in log T. Figures go next to index.md as PNG and into results/<year>/figures as PDF;
the table goes to results/<year>/summary.csv.

    .venv/bin/python analyze.py --year 2025
"""
import argparse
import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

import exam

MODELS = {"claude-haiku-4-5": "Haiku 4.5", "claude-sonnet-5": "Sonnet 5",
          "claude-opus-5-5": "Opus 5.5", "claude-fable-5-1": "Fable 5.1"}
THINKING_OPTIONAL = ("claude-haiku-4-5", "claude-sonnet-5")
EFFORTS = ["low", "medium", "high"]
INK, INK2, MUTED, GRID_C, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
EFFORT_COLOR = {"low": "#6da7ec", "medium": "#2a78d6", "high": "#104281", None: INK2}  # validated ordinal ramp; None: Haiku
MODEL_COLOR = {"claude-haiku-4-5": "#2a78d6", "claude-sonnet-5": "#eb6834",
               "claude-opus-5-5": "#1baf7a", "claude-fable-5-1": "#eda100"}  # categorical slots 1-4
MODEL_MARKER = {"claude-haiku-4-5": "o", "claude-sonnet-5": "s", "claude-opus-5-5": "^", "claude-fable-5-1": "D"}
PHASE_COLOR = {"latency": "#898781", "thinking": "#eb6834", "writing": "#2a78d6"}
HUMAN_RECORD = 63
STUDENT_SATURATION = 115
TICKS = [5, 10, 20, 30, 60, 120, 300, 720]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "axes.grid": True, "grid.color": GRID_C, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titlesize": 10, "axes.titleweight": "bold",
    "font.size": 9, "legend.frameon": False, "legend.fontsize": 8, "pdf.fonttype": 42,
})


@dataclass
class Config:
    tag: str
    model: str
    effort: str | None
    no_thinking: bool
    prompt: str
    grid: np.ndarray
    runs: list = field(repr=False)

    @property
    def label(self) -> str:
        if self.model == "claude-haiku-4-5":
            base = f"Haiku 4.5, thinking {'off' if self.no_thinking else 'on'}"
        else:
            base = f"{MODELS[self.model]}, {self.effort}" + (", thinking off" if self.no_thinking else "")
        return base + ("" if self.prompt == "default" else f", {self.prompt} prompt")

    @property
    def campaign(self) -> bool:
        """In the main design: the standard prompt, and thinking off only where the setting takes effect."""
        return self.prompt == "default" and (not self.no_thinking or self.model in THINKING_OPTIONAL)

    @property
    def low(self) -> bool:
        """The low-effort comparison; Haiku 4.5, which has no effort levels, counts as low."""
        return self.campaign and (self.effort == "low" or self.model == "claude-haiku-4-5")

    def scores(self, key: str = "score") -> np.ndarray:
        """runs × grid"""
        return np.array([[r["at"][str(T)][key] for T in self.grid] for r in self.runs], float)

    def finals(self, key: str = "score") -> np.ndarray:
        return np.array([r["at"]["final"][key] for r in self.runs], float)

    def phase(self, name: str) -> np.ndarray:
        get = {
            "startup": lambda r: r["t_startup"],
            "latency": lambda r: r["t_message_start"],
            "thinking": lambda r: r["t_first_text"] - r["t_message_start"],
            "writing": lambda r: r["t_end"] - r["t_first_text"],
            "done": lambda r: r["t_end"],
            "first_text": lambda r: r["t_first_text"],
            "chars_per_s": lambda r: r["chars"] / (r["t_end"] - r["t_first_text"]),
            "tokens_per_s": lambda r: r["usage"]["output_tokens"] / (r["t_end"] - r["t_message_start"]),
            "thinking_tokens": lambda r: ((r["usage"] or {}).get("output_tokens_details") or {}).get("thinking_tokens", 0),
            "thinking_blocks": lambda r: sum(b[0] in ("thinking", "redacted_thinking") for b in r["blocks"]),
            "text_blocks": lambda r: sum(b[0] == "text" for b in r["blocks"]),
            "max_gap": lambda r: r["max_gap"],
        }[name]
        return np.array([get(r) for r in self.runs], float)


def load(year: str) -> list[Config]:
    out = []
    for f in sorted((exam.ROOT / "results" / year).glob("*.json")):
        d = json.loads(f.read_text())
        c = d["config"]
        out.append(Config(d["tag"], c["model"], c["effort"], c.get("no_thinking", False), c.get("prompt", "default"),
                          np.array(d["grid"]), d["runs"]))
    order = {m: i for i, m in enumerate(MODELS)}
    return sorted(out, key=lambda c: (order[c.model], c.no_thinking, not c.campaign,
                                      EFFORTS.index(c.effort) if c.effort in EFFORTS else -1, c.prompt))


def mean_sd(x: np.ndarray, axis=0):
    return x.mean(axis), (x.std(axis, ddof=1) if x.shape[axis] > 1 else np.zeros_like(x.mean(axis)))


def at(c: Config, T: float, key: str = "score") -> np.ndarray:
    """Per-run score at budget T, interpolated linearly in log T between grid points."""
    lg = np.log(c.grid)
    return np.array([np.interp(np.log(T), lg, row) for row in c.scores(key)])


def crossing(c: Config, level: float, key: str = "score") -> float | None:
    """First budget at which the mean curve reaches `level`, interpolated in log T."""
    mean = c.scores(key).mean(0)
    hit = np.nonzero(mean >= level)[0]
    if not hit.size:
        return None
    i = hit[0]
    if i == 0:
        return float(c.grid[0])
    lo, hi = np.log(c.grid[i - 1]), np.log(c.grid[i])
    return float(np.exp(lo + (level - mean[i - 1]) / (mean[i] - mean[i - 1]) * (hi - lo)))


def length_time_r(c: Config) -> float:
    """Pearson r between an answer's length and the time it took to write, pooled over the runs."""
    pairs = np.array([(r["lengths"][q], s[1] - s[0]) for r in c.runs for q, s in r["splits"].items()
                      if q in r["lengths"]])  # an empty answer has a header but no length
    return float(np.corrcoef(pairs.T)[0, 1])


def overlap(configs: list[Config]) -> dict[tuple[str, int], float]:
    """Mean number of other runs in progress during each run (time-weighted)."""
    spans = [(c.tag, i, r["wall_start"], r["wall_end"]) for c in configs for i, r in enumerate(c.runs) if r.get("wall_start")]
    out = {}
    for tag, i, a, b in spans:
        busy = sum(max(0.0, min(b, b2) - max(a, a2)) for t2, j, a2, b2 in spans if (t2, j) != (tag, i))
        out[tag, i] = busy / (b - a)
    return out


def save(fig, name: str, year: str, post_dir: Path):
    figdir = exam.ROOT / "results" / year / "figures"
    figdir.mkdir(parents=True, exist_ok=True)
    fig.savefig(post_dir / f"{name}-{year}.png", dpi=220, bbox_inches="tight")
    fig.savefig(figdir / f"{name}-{year}.pdf", bbox_inches="tight")
    plt.close(fig)


def log_time_axis(ax, xmax: float, xmin: float = 5):
    ax.set_xscale("log")
    ax.set_xlim(xmin, xmax)
    ticks = [t for t in TICKS if xmin <= t <= xmax]
    ax.set_xticks(ticks, [str(t) for t in ticks])
    ax.minorticks_off()


def draw_curves(ax, c: Config, color: str, key: str, label: str, ls="-", runs=True, band=0.18, marker=None):
    S, g = c.scores(key), c.grid
    if runs:
        for row in S:
            ax.plot(g, row, color=color, lw=0.6, alpha=0.3, ls=ls)
    mean, sd = mean_sd(S)
    # ±1 SD, but never outside the range the runs actually span: the rise is steep and runs finish at different times
    ax.fill_between(g, np.maximum(mean - sd, S.min(0)), np.minimum(mean + sd, S.max(0)), color=color, alpha=band, lw=0)
    ax.plot(g, mean, color=color, lw=2, ls=ls, marker=marker, markevery=3, ms=4, label=f"{label} (n={len(S)})")


def score_axes(ax, full: float):
    ax.axhline(full, color=AXIS, lw=1, ls=":")
    log_time_axis(ax, 720)
    ax.set_ylim(0, full * 1.06)
    ax.text(720 / 1.04, full, f"max {full}", color=INK2, fontsize=7, ha="right", va="bottom")


def panel(ax, i: int, title: str):
    ax.set_title(f"({'abcdefgh'[i]}) {title}", loc="left")


def fig_panels(configs, year, post_dir, thinking: bool, full: float, ylabel: str):
    """One panel per model, one curve per effort level: every configuration with thinking on, or with it off."""
    sel = [c for c in configs if c.campaign and c.no_thinking != thinking]
    models = [m for m in MODELS if any(c.model == m for c in sel)]
    if not models:
        return
    ncol = 2 if len(models) == 4 else len(models)
    nrow = -(-len(models) // ncol)
    fig, axes = plt.subplots(nrow, ncol, figsize=(3.5 * ncol + 0.4, 3.1 * nrow + 0.3), sharex=True, sharey=True,
                             squeeze=False)
    for i, (ax, m) in enumerate(zip(axes.flat, models)):
        for c in (c for c in sel if c.model == m):
            draw_curves(ax, c, EFFORT_COLOR[c.effort], "score", c.effort or "no effort levels")
        score_axes(ax, full)
        panel(ax, i, MODELS[m])
        ax.legend(loc="upper left", title="effort" if m != "claude-haiku-4-5" else None, title_fontsize=8)
    for ax in axes.flat[len(models):]:
        ax.set_visible(False)
    for ax in axes[-1]:
        ax.set_xlabel("time budget $T$ (s)")
    for ax in axes[:, 0]:
        ax.set_ylabel(ylabel)
    fig.suptitle(f"Thinking {'on' if thinking else 'off'} · {year} exam", x=0.01, ha="left", fontsize=11,
                 fontweight="bold")
    fig.tight_layout()
    save(fig, "thinking-on" if thinking else "thinking-off", year, post_dir)


def fig_low(configs, year, post_dir, key, full, name, ylabel, extra=None):
    """Every model at low effort (Haiku 4.5 has no effort levels): thinking on solid, off dashed."""
    sel = [c for c in configs if c.low]
    if not sel:
        return
    fig, ax = plt.subplots(figsize=(6.6, 3.9))
    for c in sel:
        draw_curves(ax, c, MODEL_COLOR[c.model], key, c.label, ls="--" if c.no_thinking else "-", runs=False,
                    band=0.1, marker=MODEL_MARKER[c.model])
    score_axes(ax, full)
    if extra:
        extra(ax)
    ax.set_title(f"Every model at low effort · {year} exam", loc="left")
    ax.set_xlabel("time budget $T$ (s)")
    ax.set_ylabel(ylabel)
    legend_below(ax)
    fig.tight_layout()
    save(fig, name, year, post_dir)


def legend_below(ax):
    """Up to eight long labels: below the axes, where they hide no curve."""
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)


def mark_humans(ax):
    ax.axhline(STUDENT_SATURATION, color=MUTED, lw=1, ls="--")
    ax.text(ax.get_xlim()[0] * 1.08, STUDENT_SATURATION - 2, "115: student done", color=INK2, fontsize=7, va="top")
    ax.plot([720], [HUMAN_RECORD], marker="*", ms=11, color=INK, clip_on=False, zorder=5)
    ax.annotate("human record\n(12 min)", (720, HUMAN_RECORD), xytext=(-8, -4), textcoords="offset points",
                ha="right", va="top", fontsize=7, color=INK2)


def fig_timing(configs, year, post_dir):
    rows = configs[::-1]
    y = np.arange(len(rows))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.2, 0.42 * len(rows) + 1.3), sharey=True,
                                 gridspec_kw={"width_ratios": [1, 2.6]})
    for yy, c in zip(y, rows):
        for x, (mk, col, lab) in [(c.phase("startup"), ("o", MUTED, "Claude Code start-up (not counted)")),
                                  (c.phase("latency"), ("s", INK2, "request → first response"))]:
            m, s = mean_sd(x)
            a1.errorbar(m, yy, xerr=s, fmt=mk, color=col, ms=6, capsize=2, lw=1, label=lab if yy == y[-1] else None)
        left = 0.0
        for ph in ("latency", "thinking", "writing"):
            m = c.phase(ph).mean()
            a2.barh(yy, m, left=left, color=PHASE_COLOR[ph], height=0.62, edgecolor=SURFACE, lw=1,
                    label={"latency": "request → first response", "thinking": "thinking (nothing written)",
                           "writing": "writing"}[ph] if yy == y[-1] else None)
            left += m
        m, s = mean_sd(c.phase("done"))
        a2.errorbar(m, yy, xerr=s, fmt="none", ecolor=INK, capsize=2, lw=1)
    a1.set_yticks(y, [c.label for c in rows])
    a1.set_xlabel("seconds (mean ± SD)")
    a1.set_xlim(left=0)
    panel(a1, 0, "Warm-up")
    a2.set_xlabel("seconds from the request (mean; error bar: SD of the total)")
    panel(a2, 1, "Where the time goes")
    fig.suptitle(f"Timing · {year} exam", x=0.01, ha="left", fontsize=11, fontweight="bold")
    for a in (a1, a2):
        a.grid(axis="y", visible=False)
    handles = [h for a in (a1, a2) for h in a.get_legend_handles_labels()[0]]
    labels = [lab for a in (a1, a2) for lab in a.get_legend_handles_labels()[1]]
    seen = {}
    for h, lab in zip(handles, labels):
        seen.setdefault(lab, h)
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    fig.legend(seen.values(), seen.keys(), loc="lower center", ncol=len(seen), fontsize=7.5)
    save(fig, "timing", year, post_dir)


def fig_questions(configs, year, post_dir, m):
    qs = sorted(q for qs in m["sections"].values() for q in qs)
    M = np.array([[np.mean([r["at"]["final"]["points"].get(str(q), 0) for r in c.runs]) for q in qs] for c in configs])
    cmap = LinearSegmentedColormap.from_list("blue", ["#f0f5fc", "#9ec5f4", "#2a78d6", "#0d366b"])
    fig, ax = plt.subplots(figsize=(0.52 * len(qs) + 2.6, 0.4 * len(configs) + 1.1))
    im = ax.imshow(M, cmap=cmap, vmin=0, vmax=m["points_per_question"], aspect="auto")
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            ax.text(j, i, f"{M[i, j]:.1f}".rstrip("0").rstrip("."), ha="center", va="center", fontsize=7,
                    color=SURFACE if M[i, j] > 7 else INK)
    ax.set_xticks(range(len(qs)), [str(q) for q in qs])
    ax.set_yticks(range(len(configs)), [c.label for c in configs])
    ax.set_xlabel("question")
    ax.set_title(f"Mean points per question · {year} exam", loc="left")
    ax.grid(False)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label("mean points of 12 (complete answers)")
    cb.outline.set_visible(False)
    fig.tight_layout()
    save(fig, "questions", year, post_dir)


def fig_splits(configs, year, post_dir, m):
    """When each answer was finished, for the low-effort comparison."""
    sel = [c for c in configs if c.low]
    if not sel:
        return
    qs = sorted(q for qq in m["sections"].values() for q in qq)
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    for d, c in zip(np.linspace(-0.25, 0.25, len(sel)), sel):
        F = np.array([[r["splits"].get(str(q), [np.nan, np.nan])[1] for q in qs] for r in c.runs])
        mean, sd = np.nanmean(F, 0), np.nanstd(F, 0, ddof=1) if len(F) > 1 else np.zeros(len(qs))
        ax.errorbar(np.array(qs) + d, mean, yerr=sd, fmt=MODEL_MARKER[c.model] + ("--" if c.no_thinking else "-"),
                    ms=4, lw=1.2, capsize=1.5, color=MODEL_COLOR[c.model], label=c.label)
    ax.set_xticks(qs)
    ax.set_title(f"When each answer was finished, every model at low effort · {year} exam", loc="left")
    ax.set_xlabel("question")
    ax.set_ylabel("answer finished at (s), mean ± SD")
    legend_below(ax)
    fig.tight_layout()
    save(fig, "splits", year, post_dir)


VARIANT_COLOR = {"standard": "#2a78d6", "thinking off": "#eb6834", "speed prompt": "#1baf7a"}


def fig_variants(configs, year, post_dir, full, ylabel):
    """Each variant (thinking off, speed prompt) against the standard configuration it modifies."""
    bases = [c for c in configs if c.campaign and not c.no_thinking
             and any(v.model == c.model and v.effort == c.effort and not v.campaign for v in configs)]
    if not bases:
        return
    fig, axes = plt.subplots(1, len(bases), figsize=(3.6 * len(bases) + 0.4, 3.4), sharey=True, squeeze=False)
    for ax, b in zip(axes[0], bases):
        for c in [b] + [v for v in configs if v.model == b.model and v.effort == b.effort and not v.campaign]:
            kind = "standard" if c is b else ("thinking off" if c.no_thinking else "speed prompt")
            draw_curves(ax, c, VARIANT_COLOR[kind], "score", kind)
        score_axes(ax, full)
        ax.set_title(f"{MODELS[b.model]}, {b.effort}", loc="left")
        ax.set_xlabel("time budget $T$ (s)")
        ax.legend(loc="upper left")
    axes[0][0].set_ylabel(ylabel)
    fig.tight_layout()
    save(fig, "variants", year, post_dir)


def scale(m: dict) -> tuple[int, int, int]:
    """Number of questions, the maximum for all answers, and the maximum of the exam's own quota."""
    n = sum(len(qs) for qs in m["sections"].values())
    return n, n * m["points_per_question"], sum(m["quota"].values()) * m["points_per_question"]


YEAR_STYLE = [dict(color=MUTED, mfc=SURFACE, marker="o"), dict(color="#2a78d6", mfc="#2a78d6", marker="o")]


def fig_years(years: list[str], post_dir: Path):
    """The same configuration on two exams, side by side; the exams differ, so this compares, it does not pool."""
    by_year = [{c.tag: c for c in load(y) if c.campaign} for y in years]
    tags = [t for t in by_year[0] if all(t in b for b in by_year[1:])]
    if not tags:
        return
    n, full, full120 = scale(exam.meta(years[0]))
    rows = tags[::-1]
    y = np.arange(len(rows))
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 0.36 * len(rows) + 1.6), sharey=True,
                             gridspec_kw={"width_ratios": [1.3, 1, 1]})
    panels = [("Final score", f"score of {full} (mean ± SD)", lambda c: mean_sd(c.finals())),
              ("First word", "seconds from the request (mean ± SD)", lambda c: mean_sd(c.phase("first_text"))),
              ("Beats the human record", f"budget where the mean passes {HUMAN_RECORD}/{full120} (s)",
               lambda c: (crossing(c, HUMAN_RECORD, "score120") or np.nan, 0.0))]
    log_ticks = [1, 5, 10, 30, 60, 120, 300, 720]
    for i, (ax, (title, xlabel, stat)) in enumerate(zip(axes, panels)):
        for k, (year, b) in enumerate(zip(years, by_year)):
            vals = np.array([stat(b[t]) for t in rows])
            yy = y + (k - (len(years) - 1) / 2) * 0.22
            ax.errorbar(vals[:, 0], yy, xerr=vals[:, 1], fmt="none", ecolor=YEAR_STYLE[k]["color"], lw=1, capsize=1.5)
            ax.plot(vals[:, 0], yy, ls="none", ms=5.5, mec=YEAR_STYLE[k]["color"], **YEAR_STYLE[k], label=f"{year} exam")
        if i:
            ax.set_xscale("log")
            ax.set_xlim(0.5, 720)
            ax.set_xticks(log_ticks, [str(t) for t in log_ticks])
            ax.minorticks_off()
        else:
            ax.axvline(full, color=AXIS, lw=1, ls=":")
        panel(ax, i, title)
        ax.set_xlabel(xlabel)
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(y, [by_year[0][t].label for t in rows])
    axes[0].legend(loc="lower left")
    fig.suptitle(f"The same configurations on the {' and '.join(years)} exams", x=0.01, ha="left", fontsize=11,
                 fontweight="bold")
    fig.tight_layout()
    save(fig, "years", "-".join(years), post_dir)


def table(configs, year, m):
    n, full, _ = scale(m)
    ov = overlap(configs)
    rows = []
    for c in configs:
        ms = lambda x: f"{np.mean(x):.1f} ± {np.std(x, ddof=1):.1f}" if len(x) > 1 else f"{np.mean(x):.1f}"
        speeds = c.phase("chars_per_s")
        solo = [s for i, (s, r) in enumerate(zip(speeds, c.runs)) if ov.get((c.tag, i), 0) < 0.05]
        busy = [s for i, s in enumerate(speeds) if ov.get((c.tag, i), 0) >= 0.05]
        fmt = lambda t: f"{t:.1f}" if t else "–"
        rows.append({
            "configuration": c.label, "tag": c.tag, "runs": len(c.runs),
            "start-up s": ms(c.phase("startup")), "latency s": ms(c.phase("latency")),
            "thinking s": ms(c.phase("thinking")), "thinking tokens": ms(c.phase("thinking_tokens")),
            "first text s": ms(c.phase("first_text")), "done s": ms(c.phase("done")),
            "writing chars/s": ms(speeds), "output tokens/s": ms(c.phase("tokens_per_s")),
            "chars/s solo vs parallel": f"{np.mean(solo):.0f} (n={len(solo)}) / {np.mean(busy):.0f} (n={len(busy)})" if solo and busy else "–",
            "thinking blocks": span(c.phase("thinking_blocks")), "text blocks": span(c.phase("text_blocks")),
            "max pause writing s": f"{c.phase('max_gap').max():.2f}", "r(length, time)": f"{length_time_r(c):.2f}",
            **{f"S({T}s)": ms(at(c, T)) for T in (10, 30, 60, 120, 300)},
            f"final /{full}": ms(c.finals()), "final /120": ms(c.finals("score120")),
            "T50 s": fmt(crossing(c, full / 2)), "T90 s": fmt(crossing(c, 0.9 * full)),
            "T63/120 s": fmt(crossing(c, HUMAN_RECORD, "score120")),
            "T115/120 s": fmt(crossing(c, STUDENT_SATURATION, "score120")),
            "flags": "; ".join(sorted({f for r in c.runs for f in flags(r, c, n)})) or "–",
        })
    path = exam.ROOT / "results" / year / "summary.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(" | ".join(f"{k}: {v}" for k, v in r.items() if k != "tag"))
    print(f"\n-> {path}")


def span(x: np.ndarray) -> str:
    lo, hi = int(x.min()), int(x.max())
    return str(lo) if lo == hi else f"{lo}–{hi}"


def flags(r: dict, c: Config, n: int) -> list[str]:
    out = []
    if r.get("cut"):
        out.append("cut at the time limit")
    if r.get("stop_reason") == "max_tokens":
        out.append("hit max tokens")
    if r.get("t_message_start", 0) > 10:
        out.append("slow first response (>10 s)")
    if any(s[1] not in ("status",) for s in r.get("cli_system") or []):
        out.append("CLI system events: " + ",".join(sorted({s[1] for s in r["cli_system"] if s[1] != "status"})))
    if c.no_thinking and ((r["usage"] or {}).get("output_tokens_details") or {}).get("thinking_tokens"):
        out.append("thought despite thinking off")
    if len(r["order"]) < n:
        out.append(f"only {len(r['order'])} answers")
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--year", default="2025")
    p.add_argument("--out", type=Path, default=exam.ROOT.parent, help="where the PNG figures go")
    p.add_argument("--compare", nargs="+", metavar="YEAR", help="only the side-by-side figure of these years")
    args = p.parse_args()
    if args.compare:
        fig_years(args.compare, args.out)
        return

    m = exam.meta(args.year)
    configs = load(args.year)
    n, full, full120 = scale(m)
    ylabel = f"score (of {full}, all {n} answers)"
    table(configs, args.year, m)
    for thinking in (True, False):
        fig_panels(configs, args.year, args.out, thinking, full, ylabel)
    fig_low(configs, args.year, args.out, "score", full, "low", ylabel)
    quota = " + ".join(str(q) for q in m["quota"].values())
    fig_low(configs, args.year, args.out, "score120", full120, "low-120", f"exam score (of {full120}, best {quota})",
            extra=mark_humans)
    fig_timing(configs, args.year, args.out)
    fig_questions(configs, args.year, args.out, m)
    fig_splits(configs, args.year, args.out, m)
    fig_variants(configs, args.year, args.out, full, ylabel)


if __name__ == "__main__":
    main()
