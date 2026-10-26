"""fig_grid: experimental design grid (tasks x conditions, games per cell per model)."""
import sys
sys.path.insert(0, '/Users/chenghengli/Desktop/semester_project/paper/apart_2026/figures/src')
from style import *
from matplotlib.patches import FancyBboxPatch

setup()

W, H = TEXT_W, 2.35
fig = plt.figure(figsize=(W, H))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis('off')

# ---------------------------------------------------------------- data
tasks = ['Records', 'Pricing', 'Exam', 'Approvals']
conds = [
    # name, what it tests (two lines), games per task (None = not run)
    ('Cheap',      'can the team\ndo the task?',   [20, 20, 20, 20]),
    ('Moderate',   'will they cut\ncorners?',      [20, 20, 20, 20]),
    ('Blocked',    'break the rule\nwhen stuck?',  [20, 20, 20, 20]),
    ('Asked',      'refuse a direct\nrequest?',    [10, 10, 10, 10]),
    ('Instructed', 'follow an order\nto pool?',    [10, 10, 10, 10]),
    ('Permitted',  'share when\nallowed?',         [20, 20, 20, 20]),
    ('Solo score', 'without a\nteam score?',       [None, None, 20, 20]),
]
BLOCKED = 2

# ---------------------------------------------------------------- geometry (inches)
x0 = 0.80            # left edge of condition columns
cw = 0.705           # condition column width
gap = 0.16           # gap between the two groups
xt = x0 + 7 * cw + gap + 0.08   # left edge of totals column
tw = W - xt          # totals column width

def cx(j):
    return x0 + (j + 0.5) * cw + (gap if j >= 3 else 0)

y_group = H - 0.10
y_name = H - 0.40
y_test = H - 0.60
row_top = H - 0.86
rh = 0.235
y_rows = [row_top - (i + 0.5) * rh for i in range(4)]
y_sum = row_top - 4 * rh - 0.20
y_foot = 0.07

# ---------------------------------------------------------------- blocked column band
bx = cx(BLOCKED) - cw / 2 + 0.03
band_top = y_name + 0.13
band_bot = y_sum - 0.13
ax.add_patch(FancyBboxPatch((bx, band_bot), cw - 0.06, band_top - band_bot,
                            boxstyle='round,pad=0,rounding_size=0.05',
                            fc=ACCENT_SOFT, ec='none', alpha=0.55, zorder=0))

# ---------------------------------------------------------------- group headers
groups = [(0, 2, 'Official route quality', 'no pressure'),
          (3, 6, 'Pressure tests', 'all on the moderate route')]
for a, b, title, sub in groups:
    xl = cx(a) - cw / 2 + 0.04
    xr = cx(b) + cw / 2 - 0.04
    # title in ink + qualifier in grey, centred together on one line
    t1 = ax.text(0, y_group, title, ha='left', va='top', fontsize=8.5, color=INK)
    t2 = ax.text(0, y_group, '  ' + sub, ha='left', va='top', fontsize=7.5,
                 color=GREY)
    r = fig.canvas.get_renderer()
    inv = ax.transData.inverted()
    def width(t):
        bb = t.get_window_extent(r)
        return inv.transform((bb.x1, 0))[0] - inv.transform((bb.x0, 0))[0]
    w1, w2 = width(t1), width(t2)
    start = (xl + xr) / 2 - (w1 + w2) / 2
    t1.set_x(start)
    t2.set_x(start + w1)
    t2.set_y(y_group - 0.012)
    ax.plot([xl, xr], [y_group - 0.20, y_group - 0.20], color=LIGHT, lw=0.7,
            solid_capstyle='butt')

# ---------------------------------------------------------------- column headers
for j, (name, test, cells) in enumerate(conds):
    col = ACCENT if j == BLOCKED else INK
    ax.text(cx(j), y_name, name, ha='center', va='center', fontsize=8.2, color=col)
    ax.text(cx(j), y_test, test, ha='center', va='center', fontsize=7,
            color=ACCENT if j == BLOCKED else GREY, linespacing=1.15)

ax.text(0.05, y_name, 'Task', ha='left', va='center', fontsize=8.2,
        color=GREY)
ax.text(xt + tw / 2, y_name, 'Games', ha='center', va='center', fontsize=8.2, color=INK)
ax.text(xt + tw / 2, y_test, 'per model', ha='center', va='center',
        fontsize=7, color=GREY)

# rule under the header block
ax.plot([0.05, W - 0.02], [row_top + 0.02, row_top + 0.02], color=GREY, lw=0.6)

# ---------------------------------------------------------------- body
for i, task in enumerate(tasks):
    y = y_rows[i]
    ax.text(0.05, y, task, ha='left', va='center', fontsize=8.2, color=INK)
    tot = 0
    for j, (_, _, cells) in enumerate(conds):
        v = cells[i]
        if v is None:
            ax.text(cx(j), y, '—', ha='center', va='center', fontsize=8,
                    color=LIGHT)
            continue
        tot += v
        col = ACCENT if j == BLOCKED else INK
        ax.text(cx(j), y, f'{v}', ha='center', va='center', fontsize=8.2,
                color=col)
    ax.text(xt + tw / 2, y, f'{tot}', ha='center', va='center', fontsize=8.2,
            color=INK)
    if i < 3:
        ax.plot([0.05, W - 0.02], [y - rh / 2, y - rh / 2], color=FAINT, lw=0.6,
                zorder=0.5)

# column sums
ax.plot([0.05, W - 0.02], [row_top - 4 * rh, row_top - 4 * rh], color=GREY, lw=0.6)
ax.text(0.05, y_sum, 'All tasks', ha='left', va='center', fontsize=7.5,
        color=GREY)
grand = 0
for j, (_, _, cells) in enumerate(conds):
    s = sum(v for v in cells if v)
    grand += s
    ax.text(cx(j), y_sum, f'{s}', ha='center', va='center', fontsize=7.5,
            color=ACCENT if j == BLOCKED else GREY)
ax.text(xt + tw / 2, y_sum, f'{grand}', ha='center', va='center', fontsize=8.5, color=INK)

# ---------------------------------------------------------------- footer
ax.text(0.05, y_foot,
        'Every cell uses the same 20 matched synthetic worlds '
        '(10-game cells: 10 of them).',
        ha='left', va='bottom', fontsize=7, color=GREY)
ax.text(W - 0.02, y_foot,
        f'{grand} games per model × 13 model versions = 5,720 games',
        ha='right', va='bottom', fontsize=7.5, color=INK)

save(fig, 'fig_grid')
