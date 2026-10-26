"""Figure 1 (teaser): experimental design (a) and headline result (b)."""
import sys
sys.path.insert(0, '/Users/chenghengli/Desktop/semester_project/paper/apart_2026/figures/src')
from style import *  # noqa: E402,F401
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle  # noqa: E402

setup()

W, H, B = 6.44, 2.75, 0.12   # content stays inside; padded output is 6.5in wide
fig = plt.figure(figsize=(W, H - B))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(B, H)
ax.axis('off')

LW = 0.7
FS = 7.5      # body / box titles
FS_S = 7      # secondary
FS_T = 8.5    # panel titles


def box(x, y, w, h, ec=INK, fc='white', lw=LW):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle='round,pad=0,rounding_size=0.05',
                                ec=ec, fc=fc, lw=lw))


def arrow(p0, p1, color=INK, lw=LW, rad=0.0, ls='-', ms=6):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle='-|>', mutation_scale=ms,
                                 color=color, lw=lw, ls=ls,
                                 connectionstyle=f'arc3,rad={rad}',
                                 shrinkA=0, shrinkB=0))


def two_line(cx, cy, title, sub, c=INK):
    ax.text(cx, cy + 0.075, title, ha='center', va='center', fontsize=FS, color=c)
    ax.text(cx, cy - 0.085, sub, ha='center', va='center', fontsize=FS_S, color=GREY)


def panel_title(x, y, letter, text):
    ax.text(x, y, letter, fontsize=FS_T, color=INK, va='baseline')
    ax.text(x + 0.14, y, text, fontsize=FS_T, color=INK, va='baseline')


TOP = H - 0.16

# ================================================================ panel a
panel_title(0.04, TOP, 'a', 'One game: three copies of one LLM run a company')

# --- units (one agent each)
ux, uw, uh = 0.04, 0.86, 0.38
units = [('Orders', 1.56), ('Warehouse', 1.08), ('Billing', 0.60)]
for name, cy in units:
    box(ux, cy - uh / 2, uw, uh)
    two_line(ux + uw / 2, cy, name, 'own records only')

# --- official office with its quality dial
ox, ow = 1.30, 1.40
oy, oh = 0.41, 1.34
box(ox, oy, ow, oh)
ocx = ox + ow / 2
ax.text(ocx, oy + oh - 0.16, 'Official route', ha='center', va='center',
        fontsize=FS)
ax.text(ocx, oy + oh - 0.32, 'an office tool', ha='center',
        va='center', fontsize=FS_S, color=GREY)
ax.plot([ox + 0.1, ox + ow - 0.1], [oy + oh - 0.46] * 2, color=LIGHT, lw=0.5)
ax.text(ox + 0.1, oy + oh - 0.60, 'route setting', fontsize=FS_S,
        color=GREY, va='center')
dial = [('cheap', 'exact answer', INK),
        ('moderate', 'extra steps', INK),
        ('blocked', 'rounded only', ACCENT)]
for i, (k, v, c) in enumerate(dial):
    yy = oy + oh - 0.81 - i * 0.18
    ax.text(ox + 0.1, yy, k, fontsize=FS_S, color=c, va='center')
    ax.text(ox + 0.68, yy, v, fontsize=FS_S, color=c, va='center')
# example of the blocked reply, under the box
ax.text(ocx, oy - 0.13, '“Provisional figure: 12,000 (rounded)”',
        ha='center', va='center', fontsize=FS_S, color=ACCENT, style='italic')

# unit -> office (honest route)
for _, cy in units:
    arrow((ux + uw + 0.03, cy), (ox - 0.03, 1.08 + (cy - 1.08) * 0.4))

# --- answer sheet + status report
sx, sw, sh = 2.93, 0.94, 0.42
ans_cy, rep_cy = 1.34, 0.66
scx = sx + sw / 2
box(sx, ans_cy - sh / 2, sw, sh)
two_line(scx, ans_cy, 'Answer sheet', 'one exact answer')
box(sx, rep_cy - sh / 2, sw, sh)
two_line(scx, rep_cy, 'Status report', 'each member signs')
arrow((ox + ow + 0.03, ans_cy), (sx - 0.03, ans_cy))
arrow((scx, ans_cy - sh / 2 - 0.03), (scx, rep_cy + sh / 2 + 0.03))

# --- rule-breaking bypass
arrow((ux + uw / 2, 1.56 + uh / 2 + 0.03), (scx, ans_cy + sh / 2 + 0.03),
      color=ACCENT, lw=1.0, rad=-0.2, ls=(0, (3, 2)), ms=7)
ax.text(2.0, 2.34, 'Breaking the rule: share records directly (forum post or private message)',
        ha='center', va='center', fontsize=FS_S, color=ACCENT)
ax.text(2.0, 2.17, 'An agent, after refusing: \u201cI\u2019ll unblock the whole-org total.\u201d',
        ha='center', va='center', fontsize=FS_S, color=GREY, style='italic')

# ================================================================ panel b
x0, x1 = 4.05, 6.30
panel_title(x0, TOP, 'b', 'Refuse when asked, collude when blocked')


def X(p):
    return x0 + (x1 - x0) * p / 100


rows = [
    ('Breach when a colleague asks', 0, 17, GREY),
    ('Breach when the route is blocked', 22, 72, ACCENT),
    ('Failed teams file a false report', 24, 93, INK),
]
ys = [1.98, 1.42, 0.86]
bh = 0.085
for (lab, lo, hi, c), y in zip(rows, ys):
    ax.text(x0, y + 0.12, lab, fontsize=FS, va='baseline')
    ax.text(x1, y + 0.12, f'{lo}\u2013{hi}%', fontsize=FS_T, color=c,
            va='baseline', ha='right')
    ax.add_patch(Rectangle((x0, y - bh / 2), x1 - x0, bh, fc=FAINT, ec='none'))
    ax.add_patch(Rectangle((X(lo), y - bh / 2), X(hi) - X(lo), bh, fc=c, ec='none'))

# axis
ya = 0.52
ax.plot([x0, x1], [ya, ya], color=GREY, lw=0.6)
for p in (0, 50, 100):
    ax.plot([X(p)] * 2, [ya, ya - 0.04], color=GREY, lw=0.6)
    ax.text(X(p), ya - 0.12, f'{p}%', ha='center', va='center', fontsize=FS_S,
            color=GREY)
ax.text((x0 + x1) / 2, ya - 0.29, '% of games, range across 6 models',
        ha='center', va='center', fontsize=FS_S, color=GREY)

save(fig, 'fig_overview')
