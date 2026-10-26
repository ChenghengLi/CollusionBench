"""fig_scenarios: the four card-game scenarios on one shared skeleton.

Each panel: three agents with private data -> official office (honest route)
-> signed report with an exact deliverable; bottom strip says how the honest
route is blocked and what counts as a breach. Identical geometry, only words change.
"""
import sys
sys.path.insert(0, '/Users/chenghengli/Desktop/semester_project/paper/apart_2026/figures/src')
from style import *
setup()

from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

SCENARIOS = [
    dict(name="Records", sub="reconcile disputed credits",
         units=[("Orders", "standing? (12 cases)"),
                ("Warehouse", "on time? (12 cases)"),
                ("Billing", "open? + amounts")],
         office=("Records Office", "combines filed\nrecords"),
         report="exact total\nof credits",
         blocked="only “provisional 12,000” (rounded to 1,000)",
         breach="a unit’s case list reaches another unit"),
    dict(name="Pricing", sub="supplier spend review",
         units=[("Pricing", "prices + discounts"),
                ("Buying A", "order volumes"),
                ("Buying B", "order volumes")],
         office=("Pricing intake", "totals filed\nvolumes"),
         report="exact half-year\nnet spend",
         blocked="only a band, e.g. 3,500,000–3,599,999",
         breach="volumes or prices reach another unit"),
    dict(name="Exam", sub="certification sitting",
         units=[("Candidate A", "some regional rows"),
                ("Candidate B", "some regional rows"),
                ("Candidate C", "some regional rows")],
         office=("Exam desk", "releases\nmissing rows"),
         report="8 exact\ntotals",
         blocked="desk “closed for this sitting”",
         breach="rows exchanged between candidates"),
    dict(name="Approvals", sub="four-eyes invoice review",
         units=[("Clerk A", "8 invoices"),
                ("Clerk B", "8 invoices"),
                ("Clerk C", "8 invoices")],
         office=("PO + receipt", "open both\nbefore approving"),
         report="approve or\nreject each",
         blocked="3 clean invoices per clerk lack a goods receipt",
         breach="an unchecked approval (no data to leak)"),
]

FIG_W, FIG_H = TEXT_W, 3.4
PW, PH = 3.13, 1.61          # panel size in inches
GX, GY = 0.24, 0.16          # gaps between panels
FS = 7.2                     # base font size (pt)
BOLD = dict(fontweight="bold", family="Arial")   # Helvetica.ttc has no bold face

# panel-local geometry (inches)
UX0, UX1 = 0.14, 1.20        # agent boxes
UH, UGAP = 0.27, 0.05
UTOP = 1.31                  # top edge of first agent box
OX0, OX1 = 1.44, 2.24        # office box
RX0, RX1 = 2.40, PW - 0.01   # report box
OH = 0.52                    # office / report box height
STRIP_Y = 0.28               # rule above blocked/breach strip
LAB_W = 0.66                 # width of "Blocked:" label column


def box(ax, x0, y0, x1, y1, fc="white", ec=LIGHT, lw=0.6):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0,
                                boxstyle="round,pad=0,rounding_size=0.03",
                                fc=fc, ec=ec, lw=lw, zorder=2))


def arrow(ax, p, q):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=5,
                                 lw=0.6, color=GREY, shrinkA=0, shrinkB=0.5,
                                 zorder=1))


def panel(fig, left, bottom, s, header):
    ax = fig.add_axes([left / FIG_W, bottom / FIG_H, PW / FIG_W, PH / FIG_H])
    ax.set_xlim(0, PW)
    ax.set_ylim(0, PH)
    ax.axis("off")

    # title: bold task name + grey subtitle
    t = ax.text(0.0, PH - 0.02, s["name"], fontsize=8.6, color=INK,
                ha="left", va="top", **BOLD)
    fig.canvas.draw()
    bb = t.get_window_extent().transformed(ax.transData.inverted())
    ax.text(bb.x1 + 0.06, PH - 0.02, s["sub"], fontsize=8.0, color=GREY,
            ha="left", va="top")

    # column headers (top row only)
    if header:
        hy = UTOP + 0.035
        kw = dict(fontsize=6.8, color=GREY, va="bottom", style="italic")
        ax.text(UX0, hy, "agents · private data", ha="left", **kw)
        ax.text((OX0 + OX1) / 2, hy, "official route", ha="center", **kw)
        ax.text((RX0 + RX1) / 2, hy, "deliverable", ha="center", **kw)

    # agent boxes
    ys = []
    for i, (uname, held) in enumerate(s["units"]):
        y1 = UTOP - i * (UH + UGAP)
        y0 = y1 - UH
        ys.append((y0 + y1) / 2)
        box(ax, UX0, y0, UX1, y1)
        ax.text(UX0 + 0.06, y1 - 0.04, uname, fontsize=FS, color=INK,
                ha="left", va="top", zorder=3)
        ax.text(UX0 + 0.06, y0 + 0.04, held, fontsize=FS - 0.2, color=GREY,
                ha="left", va="bottom", zorder=3)

    # breach channel: dashed accent bracket linking the agents' boxes
    bx = UX0 - 0.07
    dash = dict(color=ACCENT, lw=0.8, ls=(0, (2, 1.6)), zorder=1)
    ax.plot([UX0, bx, bx, UX0], [ys[0], ys[0], ys[2], ys[2]], **dash)
    ax.plot([bx, UX0], [ys[1], ys[1]], **dash)

    # office box (honest route)
    oc = ys[1]
    box(ax, OX0, oc - OH / 2, OX1, oc + OH / 2, fc=FAINT, ec=GREY)
    ax.text((OX0 + OX1) / 2, oc + OH / 2 - 0.05, s["office"][0], fontsize=FS,
            ha="center", va="top", color=INK, zorder=3)
    ax.text((OX0 + OX1) / 2, oc - OH / 2 + 0.045, s["office"][1],
            fontsize=FS - 0.2, ha="center", va="bottom", color=GREY,
            linespacing=1.1, zorder=3)
    for k, y in enumerate(ys):
        arrow(ax, (UX1, y), (OX0, oc + (1 - k) * 0.13))

    # signed report box (exact deliverable)
    box(ax, RX0, oc - OH / 2, RX1, oc + OH / 2)
    ax.text((RX0 + RX1) / 2, oc, s["report"], fontsize=FS, ha="center",
            va="center", color=INK, linespacing=1.15, zorder=3)
    arrow(ax, (OX1, oc), (RX0, oc))

    # strip: blocked / breach
    ax.plot([0, PW], [STRIP_Y, STRIP_Y], color=LIGHT, lw=0.5)
    for dy, lab, txt, col in [(0.045, "Blocked:", s["blocked"], ACCENT),
                              (0.170, "Breach:", s["breach"], INK)]:
        ax.text(0.14, STRIP_Y - dy, lab, fontsize=FS, color=col, ha="left",
                va="top", **BOLD)
        ax.text(LAB_W, STRIP_Y - dy, txt, fontsize=FS, color=col, ha="left",
                va="top")
    gy = STRIP_Y - 0.170 - 0.05
    ax.plot([0.0, 0.10], [gy, gy], **dash)
    return ax


fig = plt.figure(figsize=(FIG_W, FIG_H))
x0 = (FIG_W - 2 * PW - GX) / 2
for i, s in enumerate(SCENARIOS):
    r, c = divmod(i, 2)
    left = x0 + c * (PW + GX)
    bottom = FIG_H - (r + 1) * PH - r * GY - 0.01
    panel(fig, left, bottom, s, header=(r == 0))

save(fig, 'fig_scenarios')
