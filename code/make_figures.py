#!/usr/bin/env python3
"""
ToolAbstain · Paper figures generator

Outputs 4 publication-quality PNG figures + SVG vectors to ../figures/:

  Fig 1.  Cross-family longitudinal trajectory  (line chart, family×date)
  Fig 2.  Production leaderboard               (horizontal bar, all 25+ versions)
  Fig 3.  Mitigation effect                    (grouped bar, 4 conds × 3 qs + delta)
  Fig 4.  Per-category heatmap                 (provider × cat A/B/C/D/E/F)

Reads from ../data/*.json. No network. Pure stdlib + matplotlib.
"""
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib as mpl
import numpy as np

ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
FIGS = ROOT / "figures"
FIGS.mkdir(exist_ok=True)

# Dark tech style — research dashboard aesthetic
BG_DEEP   = "#0d1424"  # deep navy/black
BG_PANEL  = "#11182b"  # slightly lighter for axes face
GRID_COL  = "#2a3550"
TEXT_COL  = "#e8edf5"
SUBTEXT   = "#9aa6b9"
ACCENT    = "#00e5ff"  # cyan accent

mpl.rcParams.update({
    "font.family": ["Helvetica", "Arial", "PingFang SC", "Hiragino Sans GB", "Heiti SC", "sans-serif"],
    "font.size": 10,
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "axes.labelcolor": TEXT_COL,
    "axes.titlecolor": TEXT_COL,
    "axes.edgecolor": GRID_COL,
    "axes.facecolor": BG_PANEL,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": True,
    "axes.spines.bottom": True,
    "axes.linewidth": 0.8,
    "xtick.color": SUBTEXT,
    "ytick.color": SUBTEXT,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "text.color": TEXT_COL,
    "legend.fontsize": 9,
    "legend.facecolor": "#171f36",
    "legend.edgecolor": GRID_COL,
    "legend.labelcolor": TEXT_COL,
    "axes.grid": True,
    "grid.color": GRID_COL,
    "grid.alpha": 0.55,
    "grid.linestyle": "-",
    "grid.linewidth": 0.5,
    "figure.facecolor": BG_DEEP,
    "figure.edgecolor": BG_DEEP,
    "figure.dpi": 110,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.facecolor": BG_DEEP,
    "savefig.edgecolor": BG_DEEP,
})

# Neon-friendly family palette (saturated, distinct on dark BG)
FAMILY_COLOR = {
    "DeepSeek": "#00d4ff",  # electric cyan
    "Qwen":     "#ff4d8d",  # hot pink
    "GLM":      "#39ff77",  # neon mint
    "MiniMax":  "#c77dff",  # electric purple
    "Step":     "#ffaa33",  # bright amber
    "Kimi":     "#f0c674",  # warm tan
    "MiMo":     "#ff5fb8",  # bright magenta
    "Spark":    "#ffd700",  # signature gold
}

CAT_LABELS = {
    "A": "Action-verb",
    "B": "Long-tail",
    "C": "Multi-tool",
    "D": "Cutoff",
    "E": "Over-call",
    "F": "Borderline",
}

DATE_TO_NUM = {
    "2025-Q3": 2025.50,
    "2025-09": 2025.75, "2025-10": 2025.83, "2025-11": 2025.92,
    "2025-12": 2026.00,
    "2026-01": 2026.08, "2026-02": 2026.17, "2026-03": 2026.25, "2026-04": 2026.33,
}


# ────────────────────────────────────────────────────────────────────────
def load_all_versions():
    """Aggregate per-version score from longitudinal files."""
    versions = []  # list of dicts: {family, name, released, total, max, by_cat, errors}

    for jf in sorted(DATA.glob("longitudinal_*.json")):
        d = json.loads(jf.read_text())
        if not d.get("raw_rows"):
            continue
        # Group by version
        by_version = defaultdict(list)
        for r in d["raw_rows"]:
            by_version[r.get("version") or r.get("provider")].append(r)

        for vname, rows in by_version.items():
            family = rows[0].get("family", "DeepSeek")  # longitudinal_deepseek may lack family field
            released = rows[0].get("released", "?")
            scores = []
            errors = 0
            by_cat = defaultdict(lambda: [0, 0])  # [pass_pts, total]
            for r in rows:
                sc = r.get("scoring", {}).get("score")
                cat = r.get("cat", "?")
                if sc is None:
                    errors += 1
                else:
                    scores.append(sc)
                    by_cat[cat][0] += sc
                by_cat[cat][1] += 1
            total_pts = sum(scores)
            max_pts = len(rows)
            versions.append({
                "family": family,
                "name": vname,
                "released": released,
                "released_num": DATE_TO_NUM.get(released, 2025.50),
                "total": total_pts,
                "max": max_pts,
                "by_cat": dict(by_cat),
                "errors": errors,
                "valid_n": len(scores),
            })

    # De-dupe by name (prefer longitudinal_direct over longitudinal_all when both exist)
    by_name = {}
    for v in versions:
        key = v["name"]
        if key not in by_name or v["errors"] < by_name[key]["errors"]:
            by_name[key] = v
    return list(by_name.values())


# ────────────────────────────────────────────────────────────────────────
def fig1_longitudinal_trajectory(versions):
    """Line chart per family: x=release date, y=score/total."""
    fig, ax = plt.subplots(figsize=(10, 5.5))

    # Group by family, plot each as a line
    by_family = defaultdict(list)
    for v in versions:
        by_family[v["family"]].append(v)

    family_order = ["DeepSeek", "Qwen", "GLM", "MiniMax", "Step", "Kimi", "MiMo"]
    for fam in family_order:
        if fam not in by_family:
            continue
        # Sort by date
        rows = sorted(by_family[fam], key=lambda x: x["released_num"])
        # Skip versions with too many errors (>50%)
        valid = [r for r in rows if r["errors"] < r["max"] * 0.5]
        if not valid:
            continue
        # Skip Spark — annotated separately below
        valid_no_spark = [r for r in valid if "Spark" not in r["name"]]
        if not valid_no_spark:
            continue
        x = [r["released_num"] for r in valid_no_spark]
        y = [(r["total"] / r["max"] * 100) if r["max"] else 0 for r in valid_no_spark]
        col = FAMILY_COLOR.get(fam, "#666")
        ax.plot(x, y, marker="o", markersize=8, linewidth=2.2, color=col, label=fam, alpha=0.92)

    # Highlight Spark Qwen FP8 if present
    spark = next((v for v in versions if "Spark" in v["name"]), None)
    if spark:
        x_s = spark["released_num"]
        y_s = spark["total"] / spark["max"] * 100
        # Glow-style star: layer larger faint marker behind for neon halo
        ax.scatter([x_s], [y_s], s=900, marker="*",
                   color=FAMILY_COLOR["Spark"], edgecolor="none",
                   alpha=0.18, zorder=9)
        ax.scatter([x_s], [y_s], s=380, marker="*",
                   color=FAMILY_COLOR["Spark"], edgecolor=TEXT_COL, linewidth=1.2,
                   zorder=10, label="Lynn FP8 (Spark) ★ #1")
        # Annotation in CENTER-RIGHT area (clear of legend + trajectory lines)
        ax.annotate(f"Lynn Spark · Qwen 3.6 35B-A3B FP8\n{spark['total']:.0f}/{spark['max']} = {y_s:.0f}%  ·  #1 in study",
                    xy=(x_s, y_s - 1), xytext=(2025.95, 64),
                    fontsize=9.5, fontweight="bold", color=FAMILY_COLOR["Spark"],
                    bbox=dict(boxstyle="round,pad=0.4", facecolor=BG_PANEL,
                              edgecolor=FAMILY_COLOR["Spark"], linewidth=1.0),
                    arrowprops=dict(arrowstyle="->", color=FAMILY_COLOR["Spark"], lw=1.2,
                                    connectionstyle="arc3,rad=-0.2"))

    # Mark cutoff for "Lynn 2026-04 v3 study" reference
    ax.axvline(2026.30, color=SUBTEXT, linestyle=":", alpha=0.4, linewidth=0.9)
    ax.text(2026.30, 22, "Lynn (2026-04)\nv3 study", fontsize=8, color=SUBTEXT,
            ha="center", va="bottom")

    ax.set_xlabel("Release date")
    ax.set_ylabel("Score on ToolAbstain-31 (%)")
    ax.set_title("Cross-family longitudinal: tool-use calibration over time (2025-Q3 → 2026-Q2)")
    ax.set_ylim(20, 100)
    # X axis: convert numeric back to readable
    xticks = [2025.50, 2025.75, 2026.00, 2026.17, 2026.33]
    xlabels = ["2025-Q3", "2025-09", "2025-12", "2026-02", "2026-04"]
    ax.set_xticks(xticks)
    ax.set_xticklabels(xlabels)
    ax.legend(loc="lower left", ncol=2, frameon=True, framealpha=0.92,
              bbox_to_anchor=(0.01, 0.01))

    out = FIGS / "fig1_longitudinal_trajectory"
    fig.savefig(str(out) + ".png")
    fig.savefig(str(out) + ".svg")
    plt.close(fig)
    print(f"  ✓ {out}.png + .svg")


# ────────────────────────────────────────────────────────────────────────
def fig2_leaderboard(versions):
    """Horizontal bar chart, all versions sorted by score."""
    # Filter to versions with reasonable data (errors < 50%)
    valid = [v for v in versions if v["errors"] < v["max"] * 0.5]
    valid.sort(key=lambda x: x["total"] / x["max"] if x["max"] else 0, reverse=False)

    fig, ax = plt.subplots(figsize=(10, max(5, len(valid) * 0.32)))

    names = [v["name"] for v in valid]
    scores = [v["total"] / v["max"] * 100 if v["max"] else 0 for v in valid]
    raws = [f"{v['total']:.0f}/{v['max']}" for v in valid]
    # Spark gets gold; cloud uses family color
    colors = [FAMILY_COLOR["Spark"] if "Spark" in v["name"] else FAMILY_COLOR.get(v["family"], "#888") for v in valid]
    edge_colors = ["black" if "Spark" in v["name"] else "none" for v in valid]
    edge_widths = [2.0 if "Spark" in v["name"] else 0 for v in valid]

    y_pos = np.arange(len(valid))
    bars = ax.barh(y_pos, scores, color=colors, edgecolor=edge_colors, linewidth=edge_widths, alpha=0.95)

    # Annotate raw score on each bar
    for i, (s, raw) in enumerate(zip(scores, raws)):
        is_spark = "Spark" in valid[i]["name"]
        ax.text(s + 1.0, i, raw + ("  ★ Lynn" if is_spark else ""),
                va="center", fontsize=8.5,
                fontweight="bold" if is_spark else "normal",
                color=FAMILY_COLOR["Spark"] if is_spark else TEXT_COL)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=8.5)
    ax.set_xlabel("Score on ToolAbstain-31 (%)")
    ax.set_title("ToolAbstain-31 leaderboard · 25+ model versions across 6 families (2025-Q3 → 2026-Q2)")
    ax.set_xlim(0, 110)
    ax.grid(axis="x", alpha=0.25, linestyle="--")
    ax.grid(axis="y", visible=False)

    # Family color legend (include Spark Lynn-deployed as a separate entry)
    used_fams = list(dict.fromkeys(v["family"] for v in valid))
    handles = [plt.Rectangle((0, 0), 1, 1, color=FAMILY_COLOR.get(f, "#888")) for f in used_fams]
    legend_labels = list(used_fams)
    if any("Spark" in v["name"] for v in valid):
        handles.append(plt.Rectangle((0, 0), 1, 1, color=FAMILY_COLOR["Spark"], edgecolor="black", linewidth=1.5))
        legend_labels.append("Lynn FP8 (Spark)")
    ax.legend(handles, legend_labels, loc="lower right", ncol=2, frameon=True, framealpha=0.9, title="Family")

    out = FIGS / "fig2_leaderboard"
    fig.savefig(str(out) + ".png")
    fig.savefig(str(out) + ".svg")
    plt.close(fig)
    print(f"  ✓ {out}.png + .svg")


# ────────────────────────────────────────────────────────────────────────
def fig3_mitigation_effect():
    """Grouped bar chart: 4 conditions × 3 questions."""
    f = sorted(DATA.glob("mitigation_*.json"))[-1]
    d = json.loads(f.read_text())

    qids = ["A4", "A6", "E2"]
    conditions = ["M0_baseline", "M1_chain", "M2_parametric", "M3_combined"]
    cond_labels = {
        "M0_baseline":   "M0 baseline",
        "M1_chain":      "M1 chain prompt",
        "M2_parametric": "M2 parametric pref",
        "M3_combined":   "M3 combined (★ best)",
    }
    cond_colors = {
        "M0_baseline":   "#5a647a",  # muted slate
        "M1_chain":      "#00d4ff",  # electric cyan
        "M2_parametric": "#39ff77",  # neon mint
        "M3_combined":   "#ff5577",  # hot coral
    }

    # Aggregate
    means = {q: {} for q in qids}
    for r in d["raw_rows"]:
        if r["qid"] not in qids:
            continue
        sc = r["scoring"].get("score")
        if sc is None:
            continue
        means[r["qid"]].setdefault(r["condition"], []).append(sc)

    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    n_q = len(qids)
    n_c = len(conditions)
    bar_w = 0.18
    x = np.arange(n_q)

    for ci, cond in enumerate(conditions):
        vals = [np.mean(means[q].get(cond, [0])) for q in qids]
        bars = ax.bar(x + (ci - n_c/2 + 0.5) * bar_w, vals, bar_w,
                       label=cond_labels[cond], color=cond_colors[cond],
                       alpha=0.92, edgecolor="white", linewidth=0.5)
        # Annotate bar value — light text for readability on dark bg
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width()/2, v + 0.025, f"{v:.2f}",
                    ha="center", va="bottom", fontsize=8.5,
                    fontweight="bold" if cond == "M3_combined" else "normal",
                    color=cond_colors[cond] if v > 0 else SUBTEXT)

    # Annotate critical deltas — placed INSIDE chart, lower-left of M3 bar (no title overlap)
    annotations = [
        ("A4", "M3_combined", "+0.36 ↑\n(chain split\nfixed)", "left"),
        ("E2", "M3_combined", "+0.61 ↑\n(over-call\nfixed!)", "left"),
    ]
    accent_red = "#ff5577"
    for qid, cond, txt, side in annotations:
        i = qids.index(qid)
        v_cond = np.mean(means[qid].get(cond, [0]))
        ci = conditions.index(cond)
        x_pos = i + (ci - n_c/2 + 0.5) * bar_w
        # Position annotation BELOW bar top, inside chart, offset to left
        ax.annotate(txt, xy=(x_pos, v_cond - 0.03),
                    xytext=(x_pos - 0.42, v_cond - 0.08),
                    fontsize=8.8, color=accent_red, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor=BG_PANEL,
                              edgecolor=accent_red, linewidth=0.8),
                    arrowprops=dict(arrowstyle="->", color=accent_red, lw=1.0))

    ax.set_xticks(x)
    ax.set_xticklabels([
        "A4: git commit + push\n(SHOULD · multi-step)",
        "A6: translate + email\n(SHOULD · multi-step)",
        "E2: 翻译 我爱北京天安门\n(SHOULDN'T · trivial parametric)",
    ], fontsize=9, color=TEXT_COL)
    ax.set_ylabel("Mean score per trial (n=18 each)")
    ax.set_ylim(0, 1.18)
    ax.set_title("Targeted prompt mitigations on 3 universal failures · 9 providers × 2 trials", pad=14)
    ax.legend(loc="upper right", frameon=True, framealpha=0.92, ncol=2,
              bbox_to_anchor=(1.0, 0.99))
    ax.axhline(1.0, linestyle=":", color=SUBTEXT, alpha=0.5, linewidth=0.8)
    ax.text(2.45, 1.015, "ceiling", fontsize=8, color=SUBTEXT)

    out = FIGS / "fig3_mitigation_effect"
    fig.savefig(str(out) + ".png")
    fig.savefig(str(out) + ".svg")
    plt.close(fig)
    print(f"  ✓ {out}.png + .svg")


# ────────────────────────────────────────────────────────────────────────
def fig4_category_heatmap(versions):
    """Heatmap: providers/versions × A/B/C/D/E/F categories."""
    valid = [v for v in versions if v["errors"] < v["max"] * 0.5]
    valid.sort(key=lambda x: x["total"] / x["max"] if x["max"] else 0, reverse=True)
    valid = valid[:18]  # top 18 to keep readable

    cats = ["A", "B", "C", "D", "E", "F"]
    matrix = []
    names = []
    for v in valid:
        row = []
        for c in cats:
            stats = v["by_cat"].get(c, [0, 0])
            pct = stats[0] / stats[1] * 100 if stats[1] else 0
            row.append(pct)
        matrix.append(row)
        names.append(v["name"])

    matrix = np.array(matrix)

    fig, ax = plt.subplots(figsize=(8.5, max(4.5, len(valid) * 0.34)))
    im = ax.imshow(matrix, cmap="RdYlGn", vmin=0, vmax=100, aspect="auto")

    ax.set_xticks(range(len(cats)))
    ax.set_xticklabels([f"{c}\n{CAT_LABELS[c]}" for c in cats], fontsize=9)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8.5)

    # Annotate cells
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            v = matrix[i, j]
            color = "white" if (v < 40 or v > 75) else "black"
            ax.text(j, i, f"{v:.0f}", ha="center", va="center",
                    color=color, fontsize=8.5,
                    fontweight="bold" if v >= 95 or v <= 20 else "normal")

    cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cbar.set_label("Pass rate (%)", fontsize=9)
    ax.set_title("Per-category performance heatmap · top 18 model versions × 6 categories", pad=14)
    ax.tick_params(axis="x", which="both", bottom=False)
    ax.tick_params(axis="y", which="both", left=False)
    ax.grid(False)

    out = FIGS / "fig4_category_heatmap"
    fig.savefig(str(out) + ".png")
    fig.savefig(str(out) + ".svg")
    plt.close(fig)
    print(f"  ✓ {out}.png + .svg")


# ────────────────────────────────────────────────────────────────────────
def main():
    print(f"📊 Generating figures from {DATA}")
    versions = load_all_versions()
    print(f"  Loaded {len(versions)} unique versions")
    for v in sorted(versions, key=lambda x: x["total"]/x["max"] if x["max"] else 0, reverse=True):
        bar = "█" * int((v["total"]/v["max"]*30) if v["max"] else 0)
        err_tag = f" ({v['errors']} err)" if v["errors"] else ""
        print(f"    {v['name']:<32} {v['family']:<10} {v['released']:<10} {v['total']:>4.1f}/{v['max']:<3}  {bar}{err_tag}")

    print(f"\n💾 Writing figures to {FIGS}")
    fig1_longitudinal_trajectory(versions)
    fig2_leaderboard(versions)
    fig3_mitigation_effect()
    fig4_category_heatmap(versions)
    print(f"\n✅ Done — 4 figures (PNG + SVG) saved.")


if __name__ == "__main__":
    main()
