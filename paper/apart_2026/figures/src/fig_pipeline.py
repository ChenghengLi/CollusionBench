"""fig_pipeline: K2-Horizon training pipeline with the five evaluated checkpoints,
and where in training coordinated collusion appears (blocked records games)."""
import sys
sys.path.insert(0, '/Users/chenghengli/Desktop/semester_project/paper/apart_2026/figures/src')
from style import *
from matplotlib.patches import Polygon

setup()

# ---------------------------------------------------------------- data
X = [1, 2, 3, 4, 5]                       # evaluated checkpoints
CKPT = ["Midtraining", "RL merge", "SFT 1", "SFT 2", "Final"]
FULL_7B = [0, 2, 9, 5, 13]                # full collusion, of 20 blocked records games
FULL_37B = [0, 0, 1, 1, 4]
MSGS_7B = ["0.5", "1.5", "102.5", "63", "49"]  # median teammate messages / game

# stage chevrons: (x centre, title, what changes, evaluated?)
STAGES = [
    (0, "Pretraining\n+ midtrain 1–3", "", False),
    (1, "Midtrain 4", "mix shifts to\nagentic, reasoning", True),
    (2, "RL merge", "RL experts\nmerged", True),
    (3, "SFT 1", "199B tokens\nof SFT", True),
    (4, "SFT 2", "50B-token\nquality subset", True),
    (5, "Final update", "anti-loop, 85 (7B) or\n110 (3.7B) steps", True),
]

XMIN, XMAX = -0.55, 5.62
HALF = 0.47       # chevron half-width
NOTCH = 0.10      # chevron point depth

fig = plt.figure(figsize=(TEXT_W, 3.0))
gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.25], hspace=0.0,
                      left=0.0, right=0.95, top=1.0, bottom=0.0)
ax_p = fig.add_subplot(gs[0])
ax_d = fig.add_subplot(gs[1], sharex=ax_p)

# ---------------------------------------------------------------- pipeline
ax_p.set_xlim(XMIN, XMAX)
ax_p.set_ylim(-1.55, 1.0)
ax_p.axis("off")

Y0, Y1 = 0.15, 0.95   # chevron vertical extent
YM = (Y0 + Y1) / 2
for i, (xc, title, change, ev) in enumerate(STAGES):
    l, r = xc - HALF, xc + HALF
    first = i == 0
    pts = [(l, Y0), (r - NOTCH, Y0), (r + NOTCH * 0.0 + 0.0, YM), (r - NOTCH, Y1), (l, Y1)]
    # tip at right; notch at left for all but the first
    pts = [(l, Y0), (r - NOTCH, Y0), (r, YM), (r - NOTCH, Y1), (l, Y1)]
    if not first:
        pts.append((l + NOTCH, YM))
    face = "white" if ev else FAINT
    edge = GREY if ev else LIGHT
    ax_p.add_patch(Polygon(pts, closed=True, facecolor=face, edgecolor=edge,
                           linewidth=0.6, joinstyle="miter"))
    ax_p.text(xc + (0.03 if not first else -0.02), YM, title, ha="center", va="center",
              fontsize=7.5 if first else 8, color=GREY if not ev else INK,
              linespacing=1.1)
    if change:
        ax_p.text(xc, -0.05, change, ha="center", va="top", fontsize=7,
                  color=GREY, linespacing=1.1)

# checkpoint pins + names
for x, name in zip(X, CKPT):
    ax_p.plot([x], [-0.95], marker="o", ms=4.2, color=INK, zorder=4, clip_on=False)
    ax_p.text(x, -1.18, name, ha="center", va="top", fontsize=7.5, color=INK)
ax_p.text(0, -0.95, "evaluated\ncheckpoint", ha="center", va="center",
          fontsize=7, color=GREY, linespacing=1.1)

# ---------------------------------------------------------------- data panel
ax_d.set_xlim(XMIN, XMAX)
YLO, YHI = -6.2, 22.6
ax_d.set_ylim(YLO, YHI)
for s in ("left", "bottom"):
    ax_d.spines[s].set_visible(False)
ax_d.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

GX0, GX1 = 0.62, 5.38
for yv in (0, 10, 20):
    ax_d.plot([GX0, GX1], [yv, yv], color=FAINT if yv else LIGHT, lw=0.6, zorder=0)
    ax_d.text(GX0 - 0.05, yv, str(yv), ha="right", va="center", fontsize=7, color=GREY)

# SFT onward: where coordinated collusion appears in 7B (thin bracket)
YB = 22.2
ax_d.plot([2.55, 2.55, 5.45, 5.45], [YB - 0.9, YB, YB, YB - 0.9], color=GREY,
          lw=0.7, solid_joinstyle="miter", zorder=1)
ax_d.text(2.64, 19.0, "from SFT on, K2-7B teams talk\nand collude more", ha="left", va="top",
          fontsize=7, color=GREY, linespacing=1.15, zorder=2,
          bbox=dict(boxstyle="square,pad=0.15", fc="white", ec="none"))

# drop lines connecting each pin to its data column (exact x alignment)
for x in X:
    ax_d.plot([x, x], [0, 20], color=FAINT, lw=0.6, zorder=0)

ax_d.plot(X, FULL_37B, color=BLUE, lw=1.3, zorder=2)
ax_d.plot(X, FULL_37B, "o", color=BLUE, ms=4, mec="white", mew=0.6, zorder=3)
ax_d.plot(X, FULL_7B, color=INK, lw=1.6, zorder=2)
ax_d.plot(X, FULL_7B, "o", color=INK, ms=4.6, mec="white", mew=0.6, zorder=3)

for x, a, b in zip(X, FULL_7B, FULL_37B):
    ax_d.text(x - 0.09, a + 1.0, str(a), ha="right", va="bottom", fontsize=7, color=INK)
    bx, bha = (x - 0.09, "right") if x == 5 else (x + 0.09, "left")
    ax_d.text(bx, b - 0.9, str(b), ha=bha, va="top", fontsize=7, color=BLUE)

ax_d.text(5.12, FULL_7B[-1], "K2-7B", ha="left", va="center", fontsize=8,
          color=INK)
ax_d.text(5.12, FULL_37B[-1], "K2-3.7B", ha="left", va="center", fontsize=8,
          color=BLUE)

# row label for the chart, in the pretraining column
ax_d.text(-0.5, 10, "Full collusion\n(of 20 blocked\nrecords games)",
          ha="left", va="center", fontsize=7.5, color=INK, linespacing=1.15)

# messages row
YMSG = -4.3
ax_d.plot([GX0, GX1], [-2.3, -2.3], color=FAINT, lw=0.6, zorder=0)
ax_d.text(-0.5, YMSG, "7B messages\nper game (median)", ha="left", va="center",
          fontsize=7, color=GREY, linespacing=1.1)
for x, m in zip(X, MSGS_7B):
    ax_d.text(x, YMSG, m, ha="center", va="center", fontsize=7.5,
              color=INK)

save(fig, 'fig_pipeline')
