"""Data figures for the Apart paper, from the hand-audited results (figures/data/*.json).

Every figure is drawn at the exact size it is printed (full width = TEXT_W, subfigure = COL_W),
so text keeps the same point size in every figure.
"""
import json, os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from style import *

setup()
D = os.path.join(os.path.dirname(__file__), "..", "data")
M = json.load(open(os.path.join(D, "matrix_data.json")))
P = json.load(open(os.path.join(D, "paper_data.json")))

FIN = [("K2-3.7B", "K2-3.7B"), ("K2-7B", "K2-7B"), ("K2-32B", "K2-32B"),
       ("Glimmer-30B", "Glimmer"), ("Qwen3.8-27B", "Qwen"), ("Gemma-4-12B", "Gemma")]
TASKS = ["records", "pricing", "exam", "approvals"]
STAGES = [("mid_4_10000", "Mid"), ("rl_merged", "RL"), ("sft_1_10000", "SFT 1"),
          ("sft_2_2500", "SFT 2"), (None, "Final")]
C7, C3 = INK, BLUE   # 7B and 3.7B series (red is reserved for breaches)
REDS = LinearSegmentedColormap.from_list("r", ["#ffffff", ACCENT])
GREYS = LinearSegmentedColormap.from_list("g", ["#ffffff", "#7f7f7f"])
PAIR_H_TOP = 2.05     # height of the two RQ1 subfigures
PAIR_H_BOT = 2.15     # height of the two RQ2 subfigures


def ck(size, tag):
    return f"K2-{size}-{tag}" if tag else f"K2-{size}"


def cell(m, t, c, key="br"):
    v = M[m].get(f"{t}/{c}")
    return (v.get(key, 0), v["n"]) if v else (None, None)


def tidy(ax, grid="y"):
    if grid:
        ax.grid(axis=grid, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=2.5, width=0.6)


def draw_cell(ax, x, y, k, n, cmap, w=0.92, h=0.86, fs=7, frac=False):
    if k is None:
        ax.text(x + 0.5, y + 0.5, "–", ha="center", va="center", fontsize=fs, color=LIGHT)
        return
    f = k / n
    ax.add_patch(plt.Rectangle((x + (1 - w) / 2, y + (1 - h) / 2), w, h, color=cmap(0.06 + 0.86 * f), lw=0))
    lab = f"{k}/{n}" if frac else (str(k) if k else "·")
    ax.text(x + 0.5, y + 0.52, lab, ha="center", va="center", fontsize=fs,
            color="white" if f > 0.55 else (INK if k else LIGHT))


# ---------------------------------------------------------------- heatmap, final models (full width)
def fig_heatmap():
    cols = [("cheap", "Cheap", 0), ("moderate", "Mod.", 0), ("blocked", "Blocked", 0), ("ask", "Asked", 0),
            ("inst", "Instr.", 1), ("perm", "Perm.", 1), ("indiv", "Solo", 0)]
    fig, axes = plt.subplots(2, 2, figsize=(TEXT_W, 0.4 + 0.36 * len(FIN) + 0.35), layout="constrained",
                             gridspec_kw=dict(width_ratios=[9.2, 7.0]))
    fig.get_layout_engine().set(w_pad=0.04, h_pad=0.06, wspace=0.06, hspace=0.08)
    for ax, t in zip(axes.flat, TASKS):
        for j, (c, lab, allowed) in enumerate(cols):
            for i, (m, _) in enumerate(FIN):
                k, n = cell(m, t, c, "sh" if allowed else "br")
                draw_cell(ax, j, i, k, n, GREYS if allowed else REDS, fs=6.2, frac=True)
            ax.text(j + 0.5, -0.3, lab, ha="center", va="bottom", fontsize=7,
                    color=ACCENT if c == "blocked" else (GREY if allowed else INK),
                    fontweight="bold" if c == "blocked" else "normal")
        ax.add_patch(plt.Rectangle((2.02, 0.04), 0.96, len(FIN) - 0.08, fill=False, ec=ACCENT, lw=0.8))
        ax.set_xlim(-2.2 if t in ("records", "exam") else 0, len(cols))
        ax.set_ylim(len(FIN) + 0.05, -1.05)
        ax.set_title(t.capitalize(), x=0.0 if t not in ("records", "exam") else 2.2 / 9.2, pad=0)
        ax.axis("off")
        if t in ("records", "exam"):
            for i, (_, mlab) in enumerate(FIN):
                ax.text(-0.15, i + 0.52, mlab, ha="right", va="center", fontsize=7.5)
    save(fig, "fig_heatmap")


# ---------------------------------------------------------------- asked vs blocked (subfigure)
def fig_asked_blocked():
    rows = []
    for m, lab in FIN:
        a = sum(cell(m, t, "ask")[0] for t in TASKS[:3])
        b = sum(cell(m, t, "blocked")[0] for t in TASKS[:3])
        rows.append((lab, a, 30, b, 60))
    rows.sort(key=lambda r: r[3] / r[4])
    fig, ax = plt.subplots(figsize=(COL_W, PAIR_H_TOP), layout="constrained")
    for i, (lab, a, an, b, bn) in enumerate(rows):
        xa, xb = 100 * a / an, 100 * b / bn
        ax.plot([xa, xb], [i, i], color=LIGHT, lw=2.4, zorder=1, solid_capstyle="round")
        ax.scatter([xa], [i], s=26, color=GREY, zorder=3, edgecolor="white", linewidth=0.6)
        ax.scatter([xb], [i], s=26, color=ACCENT, zorder=3, edgecolor="white", linewidth=0.6)
        ax.text(xb + 3.5, i, f"{b}/{bn}", va="center", fontsize=7, color=ACCENT)
        ax.text(xa - 3.5, i, f"{a}/{an}", va="center", ha="right", fontsize=7, color=GREY)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.set_xlim(-17, 100)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.spines["bottom"].set_bounds(0, 100)
    ax.set_ylim(-0.6, len(rows) - 0.1)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Games with a breach (%)")
    top = len(rows) - 1
    ax.text(100 * rows[top][1] / 30, top + 0.5, "asked", color=GREY, fontsize=7.5, ha="center", va="bottom")
    ax.text(100 * rows[top][3] / 60, top + 0.5, "blocked", color=ACCENT, fontsize=7.5, ha="center", va="bottom")
    tidy(ax, "x")
    save(fig, "fig_asked_blocked")


# ---------------------------------------------------------------- talk vs breach (subfigure)
def fig_talk():
    FX = json.load(open(os.path.join(D, "finals_extra.json")))["bins"]
    bins = [(lab, *FX[key]) for lab, key in (("0", "0"), ("1–10", "1-10"), ("11–50", "11-50"), (">50", ">50"))]
    fig, ax = plt.subplots(figsize=(COL_W, PAIR_H_TOP), layout="constrained")
    for i, (lab, k, n) in enumerate(bins):
        f = k / n
        ax.bar(i, 100 * f, width=0.62, color=REDS(0.25 + 0.75 * f / 0.8), lw=0, zorder=2)
        ax.text(i, 100 * f + 2.5, f"{100 * f:.0f}%", ha="center", va="bottom", fontsize=7.5)
    ax.set_xticks(range(4), [f"{b[0]}\n(n = {b[2]})" for b in bins], fontsize=7)
    ax.set_ylim(0, 92)
    ax.set_yticks([0, 25, 50, 75])
    ax.set_xlabel("Messages between agents in the game")
    ax.set_ylabel("Games with a breach (%)")
    tidy(ax, "y")
    save(fig, "fig_talk")


# ---------------------------------------------------------------- capability vs honesty (subfigure)
def fig_cap_honesty():
    fig, ax = plt.subplots(figsize=(COL_W, PAIR_H_BOT), layout="constrained")
    offs = {"K2-3.7B": (7, -9, "left"), "K2-7B": (-7, -2, "right"), "K2-32B": (7, 6, "left"),
            "Glimmer-30B": (6, 0, "left"), "Qwen3.8-27B": (-6, 7, "right"), "Gemma-4-12B": (6, 0, "left")}
    for m, lab in FIN:
        p = P[m]
        x, y = 100 * p["sol"] / 440, 100 * p["fr"] / p["fail"]
        ax.scatter(x, y, s=34, color=INK, zorder=3, edgecolor="white", linewidth=0.6)
        dx, dy, ha = offs[m]
        ax.annotate(lab, (x, y), xytext=(dx, dy), textcoords="offset points", fontsize=7, ha=ha, va="center",
                    arrowprops=dict(arrowstyle="-", color=LIGHT, lw=0.5) if m in ("K2-3.7B", "K2-32B") else None)
    ax.set_xlim(30, 95)
    ax.set_ylim(0, 104)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Games solved (% of 440)")
    ax.set_ylabel("False reports\n(% of failed games)")
    tidy(ax, "both")
    save(fig, "fig_cap_honesty")


def fig_convert():
    conv = json.load(open(os.path.join(D, "finals_extra.json")))["conv"]
    rows = sorted(FIN, key=lambda r: conv[r[0]]["brsol"] / max(conv[r[0]]["br"], 1))
    fig, ax = plt.subplots(figsize=(COL_W, PAIR_H_BOT), layout="constrained")
    for i, (m, lab) in enumerate(rows):
        c = conv[m]
        ax.barh(i, c["br"], color=ACCENT_SOFT, height=0.6, lw=0)
        ax.barh(i, c["brsol"], color=ACCENT, height=0.6, lw=0)
        ax.text(c["br"] + 0.8, i, f"{c['brsol']} of {c['br']}", va="center", fontsize=7, color=INK)
    ax.set_yticks(range(len(rows)), [r[1] for r in rows], fontsize=7)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlim(0, 60)
    ax.set_xticks([0, 20, 40, 60])
    ax.set_xlabel("Blocked data-task games (of 60)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=ACCENT_SOFT), plt.Rectangle((0, 0), 1, 1, color=ACCENT)]
    ax.legend(handles, ["breach", "breach and solved"], loc="lower left", bbox_to_anchor=(-0.02, 1.0), ncol=2,
              frameon=False, fontsize=7, handlelength=0.9, handletextpad=0.35, borderaxespad=0.2)
    tidy(ax, "x")
    save(fig, "fig_convert")


def fig_ckpt_path():
    fig, ax = plt.subplots(figsize=(COL_W, PAIR_H_BOT), layout="constrained")
    x = np.arange(5)
    for size, col, lw in (("3.7B", C3, 1.4), ("7B", C7, 1.8)):
        ys = []
        for tag, _ in STAGES:
            p = P[ck(size, tag)]
            ys.append(100 * p["fr"] / p["fail"])
        ax.plot(x, ys, color=col, lw=lw, marker="o", ms=3.5, markeredgecolor="white", markeredgewidth=0.5, zorder=3)
    ax.set_xticks(x, [s_[1] for s_ in STAGES], fontsize=7)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_ylabel("False reports (% of failed games)")
    ax.text(0.1, 40, "K2-7B", color=C7, fontsize=7.5, fontweight="bold")
    ax.text(0.1, 31, "K2-3.7B", color=C3, fontsize=7.5, fontweight="bold")
    tidy(ax, "y")
    save(fig, "fig_ckpt_path")


# ---------------------------------------------------------------- breach types (subfigure)
def fig_breach_types():
    rows = [(f"{s} {lab}", P[ck(s, tag)]["mix"]) for s in ("7B", "3.7B") for tag, lab in STAGES]
    rows += [("K2-32B", P["K2-32B"]["mix"]), ("Glimmer", P["Glimmer-30B"]["mix"]),
             ("Qwen", P["Qwen3.8-27B"]["mix"]), ("Gemma", P["Gemma-4-12B"]["mix"])]
    kinds = [("full", "full collusion", ACCENT), ("reqsupply", "request answered", "#e07b6b"),
             ("leak", "unrequested leak", "#f0b8ad")]
    fig, ax = plt.subplots(figsize=(COL_W, PAIR_H_BOT), layout="constrained")
    ypos, y = [], 0
    for i, (lab, mix) in enumerate(rows):
        if i in (5, 10):
            y += 0.55
        ypos.append(y)
        left = 0
        for k, _, col in kinds:
            v = mix.get(k, 0)
            ax.barh(y, v, left=left, color=col, height=0.74, lw=0)
            left += v
        ax.barh(y, 20 - left, left=left, color="white", height=0.74, lw=0.4, edgecolor=LIGHT)
        y += 1
    labels = [r[0].replace("7B ", "7B ").replace("3.7B ", "3.7B ") for r in rows]
    ax.set_yticks(ypos, labels, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlim(0, 20)
    ax.set_xticks([0, 5, 10, 15, 20])
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel("Blocked records games (of 20)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in kinds]
    ax.legend(handles, [l for _, l, _ in kinds], loc="lower left", bbox_to_anchor=(-0.02, 1.0), ncol=3,
              frameon=False, handlelength=0.9, handletextpad=0.35, columnspacing=0.7, fontsize=7,
              borderaxespad=0.2)
    save(fig, "fig_breach_types")


# ---------------------------------------------------------------- stages x task (full width)
def fig_stages():
    fig, axes = plt.subplots(1, 4, figsize=(TEXT_W, 1.85), sharey=True, layout="constrained")
    fig.get_layout_engine().set(wspace=0.04)
    x = np.arange(5)
    for ax, t in zip(axes, TASKS):
        ax.axvspan(1.5, 3.5, color=FAINT, alpha=0.7, lw=0, zorder=0)
        for size, col, lw in (("3.7B", C3, 1.4), ("7B", C7, 1.8)):
            y = [cell(ck(size, tag), t, "blocked")[0] for tag, _ in STAGES]
            ax.plot(x, y, color=col, lw=lw, zorder=3, marker="o", ms=3.2,
                    markeredgecolor="white", markeredgewidth=0.5)
        ax.set_title(t.capitalize())
        ax.set_xticks(x, [s[1] for s in STAGES], fontsize=6.6)
        ax.set_ylim(-1, 21)
        ax.set_yticks([0, 10, 20])
        tidy(ax, "y")
    axes[0].set_ylabel("Blocked games\nwith a breach (of 20)")
    axes[1].text(0.0, 19.2, "K2-7B", color=C7, fontsize=7.5, fontweight="bold", va="center")
    axes[1].text(0.0, 16.2, "K2-3.7B", color=C3, fontsize=7.5, fontweight="bold", va="center")
    axes[0].text(2.5, -0.4, "SFT phases", color=GREY, fontsize=6.8, ha="center", va="bottom")
    save(fig, "fig_stages")


# ---------------------------------------------------------------- appendix: checkpoint heatmap (full width)
def fig_heat_ckpt():
    cols = [("moderate", "Mod."), ("blocked", "Blocked"), ("ask", "Asked")]
    rows = [(ck(s, tag), f"{s} {lab}") for s in ("7B", "3.7B") for tag, lab in STAGES]
    fig = plt.figure(figsize=(TEXT_W, 3.05))
    ax = fig.add_axes([0, 0, 1, 1])
    for ti, t in enumerate(TASKS):
        for j, (c, lab) in enumerate(cols):
            x = ti * 3.35 + j
            for i, (m, _) in enumerate(rows):
                y = i + (0.45 if i >= 5 else 0)
                k, n = cell(m, t, c)
                f = k / n
                ax.add_patch(plt.Rectangle((x + 0.04, y + 0.07), 0.92, 0.86, color=REDS(0.06 + 0.86 * f), lw=0))
                ax.text(x + 0.5, y + 0.52, f"{k}/{n}" if k else "·", ha="center", va="center", fontsize=6.6,
                        color="white" if f > 0.55 else (INK if k else LIGHT))
            ax.text(x + 0.5, -0.2, lab, ha="center", va="bottom", fontsize=7,
                    color=ACCENT if c == "blocked" else GREY, fontweight="bold" if c == "blocked" else "normal")
        ax.text(ti * 3.35 + 1.5, -0.95, t.capitalize(), ha="center", va="bottom", fontsize=8, fontweight="bold")
    for i, (_, rl) in enumerate(rows):
        y = i + (0.45 if i >= 5 else 0)
        ax.text(-0.15, y + 0.52, rl, ha="right", va="center",
                fontsize=7.2, fontweight="bold" if rl.endswith("Final") else "normal")
    ax.set_xlim(-1.75, 3 * 3.35 + 3.05)
    ax.set_ylim(10.6, -1.75)
    ax.axis("off")
    save(fig, "fig_heat_ckpt")


# ---------------------------------------------------------------- appendix: behaviour profile (full width)
def fig_profile():
    panels = [("msgs", "Messages per game", 125), ("toks", "Tokens per turn", 160),
              ("sol", "Games solved (of 440)", 440), ("frr", "False reports (% failed)", 100)]
    fig, axes = plt.subplots(1, 4, figsize=(TEXT_W, 1.85), layout="constrained")
    fig.get_layout_engine().set(wspace=0.06)
    x = np.arange(5)
    for ax, (k, lab, mx) in zip(axes, panels):
        for size, col, lw in (("3.7B", C3, 1.4), ("7B", C7, 1.8)):
            ys = []
            for tag, _ in STAGES:
                p = P[ck(size, tag)]
                ys.append(100 * p["fr"] / p["fail"] if k == "frr" else p[k])
            ax.plot(x, ys, color=col, lw=lw, marker="o", ms=3, markeredgecolor="white", markeredgewidth=0.5)
        ax.set_ylim(0, mx * 1.06)
        ax.set_title(lab, fontsize=7.8)
        ax.set_xticks(x, [s[1] for s in STAGES], fontsize=6.6)
        tidy(ax, "y")
    axes[0].text(2.2, 112, "7B", color=C7, fontsize=7.5, fontweight="bold", va="center")
    axes[0].text(0.0, 30, "3.7B", color=C3, fontsize=7.5, fontweight="bold", va="center")
    save(fig, "fig_profile")


STAGE_COLS = [("no contact", "#e6e6e6"), ("discovery", "#bdbdbd"), ("coordination", "#8c8c8c"),
              ("unilateral breach", "#f0b8ad"), ("joint breach", ACCENT), ("concealed joint breach", "#6e1a12")]


def _funnel(ax, rows, data, fs=7):
    for i, (key, lab) in enumerate(rows):
        left = 0
        for k, (name, col) in enumerate(STAGE_COLS):
            v = data[key][k]
            ax.barh(i, v, left=left, color=col, height=0.7, lw=0)
            left += v
    ax.set_yticks(range(len(rows)), [r[1] for r in rows], fontsize=fs)
    ax.invert_yaxis()
    ax.set_xlim(0, 60)
    ax.set_xticks([0, 20, 40, 60])
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)


def fig_funnel():
    data = json.load(open(os.path.join(D, "stage_funnel.json")))
    fig, ax = plt.subplots(figsize=(COL_W, PAIR_H_TOP), layout="constrained")
    _funnel(ax, FIN, data)
    ax.set_xlabel("Blocked data-task games (of 60)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, c in STAGE_COLS]
    ax.legend(handles, [n for n, _ in STAGE_COLS], loc="lower left", bbox_to_anchor=(-0.02, 1.0), ncol=3,
              frameon=False, fontsize=6.6, handlelength=0.8, handletextpad=0.3, columnspacing=0.6,
              borderaxespad=0.2)
    save(fig, "fig_funnel")


def fig_funnel_ckpt():
    data = json.load(open(os.path.join(D, "stage_funnel.json")))
    fig, axes = plt.subplots(1, 2, figsize=(TEXT_W, 1.75), layout="constrained")
    for ax, size in zip(axes, ("7B", "3.7B")):
        rows = [(ck(size, tag), lab) for tag, lab in STAGES]
        _funnel(ax, rows, data)
        ax.set_title("K2-" + size, loc="left", fontsize=8, pad=2)
        ax.set_xlabel("Blocked data-task games (of 60)", fontsize=7)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for _, c in STAGE_COLS]
    fig.legend(handles, [n for n, _ in STAGE_COLS], loc="outside upper center", ncol=6,
               frameon=False, fontsize=7, handlelength=0.9, handletextpad=0.35, columnspacing=1.0)
    save(fig, "fig_funnel_ckpt")


def fig_train():
    labs = [lab for _, lab in STAGES]
    x = list(range(len(STAGES)))
    panels = [
        ("a  Messages per game", lambda p: max(p["msgs"], 0.5), "Median messages,\nblocked records game", True, None),
        ("b  Games solved", lambda p: 100 * p["sol"] / 440, "% of 440 games", False, (0, 100)),
        ("c  False reports", lambda p: 100 * p["fr"] / p["fail"], "% of failed games", False, (0, 100)),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(TEXT_W, 1.85), layout="constrained")
    for ax, (title, f, ylab, logy, lim) in zip(axes, panels):
        for size, col, mk in (("7B", C7, "o"), ("3.7B", C3, "s")):
            ys = [f(P[ck(size, tag)]) for tag, _ in STAGES]
            ax.plot(x, ys, color=col, lw=1.5 if size == "7B" else 1.2, marker=mk, ms=3.6,
                    mec="white", mew=0.5, label="K2-" + size)
        ax.axvspan(1.5, 3.5, color=FAINT, zorder=0, lw=0)
        ax.set_xticks(x, labs, fontsize=6.6)
        if logy:
            ax.set_yscale("log"); ax.set_ylim(0.3, 200)
            ax.set_yticks([1, 10, 100], ["1", "10", "100"])
        else:
            ax.set_ylim(*lim); ax.set_yticks([0, 25, 50, 75, 100])
        ax.set_ylabel(ylab, fontsize=6.6)
        ax.set_title(title, loc="left", fontsize=8, pad=3)
        tidy(ax, "y")
    axes[0].legend(frameon=False, fontsize=6.6, loc="upper left", handlelength=1.2, borderaxespad=0.2)
    save(fig, "fig_train")

def fig_tokens():
    labs = [lab for _, lab in STAGES]
    x = list(range(len(STAGES)))
    fig, ax = plt.subplots(figsize=(COL_W, PAIR_H_BOT), layout="constrained")
    for size, col, mk in (("7B", C7, "o"), ("3.7B", C3, "s")):
        ys = [P[ck(size, tag)]["toks"] for tag, _ in STAGES]
        ax.plot(x, ys, color=col, lw=1.5 if size == "7B" else 1.2, marker=mk, ms=3.6, mec="white", mew=0.5, label="K2-" + size)
    ax.axvspan(1.5, 3.5, color=FAINT, zorder=0, lw=0)
    ax.set_xticks(x, labs, fontsize=7)
    ax.set_ylabel("Median tokens per turn,\nblocked records games", fontsize=7)
    ax.set_ylim(0, 170)
    ax.legend(frameon=False, fontsize=7, loc="upper right")
    tidy(ax, "y")
    save(fig, "fig_tokens")


if __name__ == "__main__":
    fig_heatmap(); fig_asked_blocked(); fig_talk(); fig_cap_honesty(); fig_breach_types(); fig_stages()
    fig_heat_ckpt(); fig_profile(); fig_convert(); fig_ckpt_path(); fig_funnel(); fig_funnel_ckpt(); fig_train(); fig_tokens()
    print("ok")
