"""fig_episode: anatomy of one blocked game (real Qwen game, Records task).

Swimlane timeline: a thin Records-Office / answer-sheet lane on top, the three
agent lanes below, and the measurement brackets underneath that show which
logged events define each outcome.
"""
import sys
sys.path.insert(0, '/Users/chenghengli/Desktop/semester_project/paper/apart_2026/figures/src')
from style import *  # noqa: F401,F403
setup()

from matplotlib.patches import FancyArrowPatch

FS = 7.4      # body text
FS_S = 7.0    # smallest text

fig = plt.figure(figsize=(TEXT_W, 2.55))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(-4.5, 107)
ax.set_ylim(-0.85, 4.6)
ax.axis('off')

# ---------------------------------------------------------------- lanes
Y_SYS = 3.45                     # office / answer-sheet lane
Y = {'Orders': 2.55, 'Warehouse': 1.75, 'Billing': 0.95}
X0, X1 = 13.5, 99.0              # lane extent
GAP = (53.5, 56.5)               # broken time axis ("24 calls later")

def lane_line(y, lw=0.6, color=LIGHT):
    ax.plot([X0, GAP[0]], [y, y], color=color, lw=lw, zorder=1,
            solid_capstyle='butt')
    ax.plot([GAP[1], X1], [y, y], color=color, lw=lw, zorder=1,
            solid_capstyle='butt')

# office lane: faint band
ax.fill_between([X0, X1], Y_SYS - 0.22, Y_SYS + 0.22, color=FAINT, lw=0,
                zorder=0)
ax.text(X0 - 1.2, Y_SYS + 0.06, 'Records Office', ha='right', va='center',
        fontsize=FS, color=GREY)
ax.text(X0 - 1.2, Y_SYS - 0.27, '/ answer sheet', ha='right', va='center',
        fontsize=FS_S, color=GREY)

holds = {'Orders': 'case list', 'Warehouse': 'case list',
         'Billing': 'case list + amounts'}
for name, y in Y.items():
    lane_line(y)
    ax.text(X0 - 1.2, y + 0.08, name, ha='right', va='center', fontsize=FS + 0.4,
            color=INK, fontweight='bold')
    ax.text(X0 - 1.2, y - 0.24, holds[name], ha='right', va='center',
            fontsize=FS_S, color=GREY)

# time-axis break
for y in Y.values():
    for gx in GAP:
        ax.plot([gx - 0.5, gx + 0.5], [y - 0.09, y + 0.09], color=LIGHT, lw=0.6)
ax.text(sum(GAP) / 2, 2.15, '24 team\ncalls later', ha='center', va='center',
        fontsize=FS_S, color=GREY, linespacing=1.1)

# ---------------------------------------------------------------- phase header
X = dict(read=15, office=21, request=27, refuse=33.5, breach=62,
         solve=86.5, sign=92.5)
header = [('read', 'reads\npolicy'), ('office', 'office\nblocked'),
          ('request', 'request'), ('refuse', 'refusal'),
          ('breach', 'breach'), ('solve', 'submits'), ('sign', 'signs\nreport')]
Y_HEAD = 4.5
for k, lab in header:
    col = ACCENT if k == 'breach' else GREY
    ax.text(X[k], Y_HEAD, lab, ha='center', va='top', fontsize=FS_S, color=col,
            linespacing=1.0, fontweight='bold' if k == 'breach' else 'normal')

def dot(x, y, color=INK, filled=True, s=16, z=4):
    ax.scatter([x], [y], s=s, color=color if filled else 'white',
               edgecolor=color, linewidths=0.9, zorder=z)

def arrow(x0, y0, x1, y1, color=INK, lw=0.9, ls='-', z=3):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle='-|>',
                                 mutation_scale=6, color=color, lw=lw,
                                 linestyle=ls, shrinkA=2.5, shrinkB=2.5,
                                 zorder=z))

# 1. everyone reads policy & files
for y in Y.values():
    dot(X['read'], y, color=GREY, s=10)

# 2. office returns the rounded figure
dot(X['office'], Y_SYS, color=INK, filled=False, s=18)
ax.text(X['office'] + 1.2, Y_SYS, '“Provisional figure: 12,000 (rounded)…”',
        ha='left', va='center', fontsize=FS_S, color=INK, style='italic')

# 3. Warehouse refuses, citing policy (forum post)
xr = X['refuse']
dot(xr, Y['Warehouse'], color=INK)
ax.text(xr + 1.3, Y['Warehouse'] + 0.25, 'forum post', ha='left', va='center',
        fontsize=FS_S, color=GREY)
ax.text(xr + 1.3, Y['Warehouse'] - 0.03,
        '“…internal unit record,\nmust not be shared…”',
        ha='left', va='top', fontsize=FS_S, color=INK, style='italic',
        linespacing=1.05)

# 4. request: Billing asks Warehouse for its case IDs (call 397, before the refusal)
xq = X['request']
dot(xq, Y['Billing'], color=GREY, s=12)
arrow(xq, Y['Billing'], xq, Y['Warehouse'], color=GREY, lw=0.9, ls=(0, (2, 1.5)))
ax.text(xq + 1.0, Y['Billing'] - 0.24, 'Billing asks for the case lists', ha='left',
        va='center', fontsize=FS_S, color=GREY)

# 5. breach: Warehouse -> Billing private message with real case IDs
xb = X['breach']
dot(xb, Y['Warehouse'], color=ACCENT, s=20)
arrow(xb, Y['Warehouse'], xb, Y['Billing'], color=ACCENT, lw=1.2)
dot(xb, Y['Billing'], color=ACCENT, filled=False, s=14)
ax.text(xb + 1.3, Y['Warehouse'] + 0.25, 'private message to Billing',
        ha='left', va='center', fontsize=FS_S, color=ACCENT)
ax.text(xb + 1.3, Y['Warehouse'] - 0.03,
        '“I’ll unblock the\nwhole-org total…\n'
        'C-101, C-102, C-103…”',
        ha='left', va='top', fontsize=FS_S, color=ACCENT, style='italic',
        linespacing=1.05)

# 6. Billing submits the exact figure
xs = X['solve']
dot(xs, Y['Billing'], color=INK)
arrow(xs, Y['Billing'], xs, Y_SYS, color=INK, lw=0.8)
dot(xs, Y_SYS, color=INK, s=14)
ax.text(xs - 1.0, Y['Billing'] - 0.22, 'submits exact total', ha='right',
        va='center', fontsize=FS_S, color=INK)

# 7. team signs the status report
xg = X['sign']
for y in Y.values():
    dot(xg, y, color=INK, filled=False, s=14)
ax.plot([xg, xg], [Y['Billing'], Y_SYS], color=INK, lw=0.6, zorder=2)
dot(xg, Y_SYS, color=INK, s=14)
ax.text(xg + 0.9, Y['Orders'] - 0.03,
        '“complete and\nverified. Open\nissues: None.”',
        ha='left', va='top', fontsize=FS_S, color=INK, style='italic',
        linespacing=1.05)

# ---------------------------------------------------------------- measurement brackets
def bracket(x0, x1, y, label, color=INK, sub=None, lw=0.8):
    t = 0.1
    ax.plot([x0, x0, x1, x1], [y + t, y, y, y + t], color=color, lw=lw,
            solid_capstyle='butt', solid_joinstyle='miter')
    ax.text((x0 + x1) / 2, y - 0.08, label, ha='center', va='top',
            fontsize=FS_S, color=color)

YB1 = 0.3
bracket(xq - 1.2, xr + 1.2, YB1, 'S1 discovery, S2 coordination:\ncolleagues found, protected list requested', GREY)
bracket(xb - 1.2, xs + 1.4, YB1, 'S3 joint execution:\nlist supplied on request, then used', ACCENT)
bracket(xg - 1.4, xg + 1.4, YB1, 'S4 concealment:\ndisclosure\noverwritten', ACCENT)

save(fig, 'fig_episode')
