"""Draw docs/img/rig-names.svg: the boat-file names on a side view and a view from astern."""
import math
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

out = sys.argv[1]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9.5, "svg.fonttype": "none"})
INK, WIRE, SPAR, DIM, SAIL, CP = "#1f2328", "#2f6db5", "#4a4a4a", "#b3541e", "#e9eef5", "#1f7a4d"

FT = 0.3048
I, J, P, E = 53.15 * FT, 15.09 * FT, 47.05 * FT, 17.06 * FT
heel, boom, above = -1.9, 1.75, 0.25
s1, s2 = 0.37 * I, 0.68 * I
bs = (-8.55, 0.30)
lowF, lowA, cap_x = 0.686, -0.483, -0.40

fig, (ax, bx) = plt.subplots(1, 2, figsize=(11.5, 7.6), gridspec_kw={"width_ratios": [1.55, 1]})


def dim(a, p0, p1, text, off=(0, 0), side="center", rot=0):
    a.annotate("", p1, p0, arrowprops=dict(arrowstyle="<->", color=DIM, lw=1.0, shrinkA=0, shrinkB=0))
    mx, my = (p0[0] + p1[0]) / 2 + off[0], (p0[1] + p1[1]) / 2 + off[1]
    a.text(mx, my, text, color=DIM, ha=side, va="center", rotation=rot, fontweight="bold")


def lab(a, x, y, text, color=INK, **kw):
    a.text(x, y, text, color=color, **kw)


# ---- side view ------------------------------------------------------------------------------------
ax.set_title("Side view (bow to the right)", loc="left", color=INK, fontsize=11)
ax.fill([-0.12, -0.12, -E], [boom, boom + P, boom], color=SAIL, zorder=0)
ax.fill([J, 0.2, -1.6], [0.0, I * 0.95, 0.9], color=SAIL, zorder=0)
ax.plot([-10.2, 7.4], [0, 0], color=INK, lw=1.2)
lab(ax, 7.45, 0.0, "sheer, z = 0", va="center", fontsize=8.5)
ax.plot([0, 0], [heel, I + above], color=SPAR, lw=4, solid_capstyle="butt")
ax.plot([0, -E], [boom, boom], color=SPAR, lw=3)
ax.plot([0, J], [I, 0], color=WIRE, lw=1.6)
lab(ax, J * 0.55 + 0.25, I * 0.45, "forestay", color=WIRE, rotation=-74)
ax.plot([0, bs[0]], [I, bs[1]], color=WIRE, lw=1.6)
lab(ax, -5.4, I * 0.45, "backstay", color=WIRE, rotation=59)
ax.plot([0, 3.9], [0.5 * I, 0], color=WIRE, lw=1.2, ls=(0, (4, 3)))
lab(ax, 2.05, 0.5 * I * 0.36, "inner_forestay\n(cutter)", color=WIRE, fontsize=8, rotation=-55)
for z in (s1, s2):
    ax.plot([-0.55, 0], [z, z], color=SPAR, lw=2)
ax.plot([lowF, 0, lowA], [0, s1, 0], color=WIRE, lw=1.0)
ax.plot([cap_x, 0], [0, I], color=WIRE, lw=0.8, alpha=0.5)

dim(ax, (-1.4, 0), (-1.4, I), "I", off=(-0.35, 0))
dim(ax, (0, -4.6), (J, -4.6), "J", off=(0, -0.55))
dim(ax, (-0.55, boom), (-0.55, boom + P), "P", off=(-0.4, 6.0))
dim(ax, (0, boom - 0.9), (-E, boom - 0.9), "E", off=(0, -0.5))
dim(ax, (1.2, 0), (1.2, boom), "gooseneck_z", off=(0.15, 0), side="left")
dim(ax, (-0.6, I), (-0.6, I + above), "", off=(0, 0))
lab(ax, -0.75, I + 0.9, "above_hounds", color=DIM, ha="right", fontweight="bold")
dim(ax, (-0.7, 0), (-0.7, heel), "heel_z (keel step)", off=(-0.15, -0.3), side="right")

lab(ax, -0.25, I + 0.35, "hounds", ha="right", fontsize=8.5)
ax.plot([lowF, lowA], [0, 0], "o", color=CP, ms=5)
dim(ax, (0, -2.5), (lowF, -2.5), "", off=(0, 0))
dim(ax, (0, -3.3), (lowA, -3.3), "", off=(0, 0))
lab(ax, lowF + 0.15, -2.5, "lowers.forward: chainplate x > 0", color=CP, va="center", fontsize=8.5)
lab(ax, lowA - 0.15, -3.3, "lowers.aft: chainplate x < 0", color=CP, va="center", ha="right", fontsize=8.5)
ax.plot(*bs, "o", color=CP, ms=5)
lab(ax, bs[0], bs[1] - 0.55, "backstay bottom\n(x, |y|, z)", color=CP, ha="center", va="top", fontsize=8.5)
ax.annotate("x", (2.6, I + 1.6), (0.4, I + 1.6), arrowprops=dict(arrowstyle="->", color=INK), va="center")
ax.annotate("z", (-1.6, I + 3.6), (-1.6, I + 1.4), arrowprops=dict(arrowstyle="->", color=INK), ha="center")
lab(ax, 2.75, I + 1.6, "forward", va="center", fontsize=8.5)
ax.set_xlim(-10.6, 9.3)
ax.set_ylim(-5.6, I + 4.2)
ax.set_aspect("equal")
ax.axis("off")

# ---- view from astern -------------------------------------------------------------------------------
bx.set_title("From astern (port on the left)", loc="left", color=INK, fontsize=11)
L1, L2, sw = 1.35, 0.81, math.radians(15)
y1, y2, ycp = L1 * math.cos(sw), L2 * math.cos(sw), 1.70
bx.plot([-2.6, 2.6], [0, 0], color=INK, lw=1.2)
bx.plot([0, 0], [heel, I + above], color=SPAR, lw=4, solid_capstyle="butt")
for sgn in (1, -1):
    bx.plot([0, -sgn * y1], [s1, s1], color=SPAR, lw=2)
    bx.plot([0, -sgn * y2], [s2, s2], color=SPAR, lw=2)
    bx.plot([-sgn * ycp, -sgn * y1, -sgn * y2, 0], [0, s1, s2, I], color=WIRE, lw=1.6)
    bx.plot([-sgn * y1, 0], [s1, s2], color=WIRE, lw=1.2)
    bx.plot([-sgn * ycp, 0], [0, s1], color=WIRE, lw=1.2)
    bx.plot([-sgn * ycp], [0], "o", color=CP, ms=5)
lab(bx, -1.68, s1 * 0.5, "V1", color=WIRE, ha="right", fontweight="bold")
lab(bx, -1.2, (s1 + s2) / 2 + 0.6, "V2", color=WIRE, ha="right", fontweight="bold")
lab(bx, -0.55, (s2 + I) / 2, "V3", color=WIRE, ha="right", fontweight="bold")
lab(bx, -0.50, (s1 + s2) / 2 - 0.2, "D2", color=WIRE, ha="left", fontweight="bold")
lab(bx, -0.72, s1 * 0.38, "D1", color=WIRE, ha="left", fontweight="bold")
lab(bx, 1.25, I * 0.86, "cap = V1 + V2 + V3\nintermediate = D2\nlowers = D1", color=WIRE, fontsize=8.5)
lab(bx, 1.25, I * 0.72, "discontinuous: V1 is its own\nwire to the lower spreader tip;\nV2 and D2 start there", color=INK, fontsize=8)
lab(bx, 1.25, I * 0.60, "continuous: cap and intermediate\neach run to their own chainplate", color=INK, fontsize=8)
dim(bx, (0, -1.0), (-ycp, -1.0), "chainplate y", off=(0, -0.55))
dim(bx, (0, s2 + 0.9), (-y2, s2 + 0.9), "", off=(0, 0))
lab(bx, -0.05, s2 + 1.6, "spreader length", color=DIM, ha="right", fontweight="bold", fontsize=8.5)
lab(bx, -y1 - 0.12, s1, "spreaders[0]", fontsize=8, ha="right", va="center")
lab(bx, -y2 - 0.12, s2, "spreaders[1]", fontsize=8, ha="right", va="center")
dim(bx, (2.0, 0), (2.0, s1), "spreader height", off=(0.15, 0), side="left")
bx.set_xlim(-3.4, 4.6)
bx.set_ylim(-5.6, I + 4.2)
bx.set_aspect("equal")
bx.axis("off")

fig.tight_layout()
fig.savefig(out, format="svg", bbox_inches="tight")
print("wrote", out)
