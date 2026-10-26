"""Shared figure style for the Apart paper. Import with: from style import *"""
import matplotlib as mpl
import matplotlib.pyplot as plt

INK = "#1f1f1f"      # main text and marks
GREY = "#6b6b6b"     # secondary text, neutral marks
LIGHT = "#bdbdbd"    # quiet marks, reference lines
FAINT = "#ececec"    # backgrounds, empty cells
ACCENT = "#c0392b"   # the one accent: rule-breaking / collusion / blocked
ACCENT_SOFT = "#f2d4cf"
BLUE = "#2e5e8c"     # second series only when two series must be told apart (e.g. 3.7B vs 7B)

TEXT_W = 6.5   # inches, full text width (letter, 1in margins)
COL_W = 3.18   # inches, half width (0.49 \textwidth, used for subfigures)

def setup():
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 8,
        "axes.titlesize": 8.5,
        "axes.labelsize": 8,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "legend.fontsize": 7.5,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "grid.color": FAINT,
        "grid.linewidth": 0.6,
        "axes.edgecolor": GREY,
        "axes.labelcolor": INK,
        "xtick.color": GREY,
        "ytick.color": GREY,
        "text.color": INK,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.linewidth": 0.6,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "lines.linewidth": 1.6,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "savefig.bbox": None,           # export at exactly figsize, so print size = design size
        "savefig.pad_inches": 0.0,
        "figure.dpi": 150,
    })

def save(fig, name, outdir=None):
    import os
    outdir = outdir or os.path.join(os.path.dirname(__file__), "..")
    fig.savefig(os.path.join(outdir, name + ".pdf"))
    fig.savefig(os.path.join(outdir, name + ".png"), dpi=200)
