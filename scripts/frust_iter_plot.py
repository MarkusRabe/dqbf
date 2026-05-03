"""Plot frust iteration progress (solved/344) as a self-contained SVG."""

from pathlib import Path

DATA = [
    (0, 154, "baseline"),
    (1, 194, "Vec clauses + occ lists"),
    (2, 225, "subsumption"),
    (3, 261, "sig + shortest-first"),
    (4, 279, "∀-expand + DPLL"),
    (5, 289, "BDD-memo Shannon"),
    (6, 289, "trail-DPLL"),
    (7, 290, "occ-prop + flat tables"),
    (8, 291, "polarity retry"),
    (9, 291, "vote + bitmask ured"),
    (10, 291, "back-subsume gate"),
]
N = 344
W, H = 720, 420


def main() -> None:
    xs = [50 + i * (W - 100) / 10 for i, _, _ in DATA]
    ys = [H - 40 - (s / N) * (H - 80) for _, s, _ in DATA]
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    bars = "".join(
        f'<rect x="{x - 12:.1f}" y="{y:.1f}" width="24" height="{H - 40 - y:.1f}" '
        f'fill="#6ab0e8"/>' for x, y in zip(xs, ys)
    )
    labels = "".join(
        f'<text x="{x:.1f}" y="{y - 6:.1f}" font-size="11" text-anchor="middle">{s}</text>'
        f'<text x="{x:.1f}" y="{H - 25:.1f}" font-size="9" text-anchor="middle">{i}</text>'
        for (i, s, _), x, y in zip(DATA, xs, ys)
    )
    yt = "".join(
        f'<line x1="46" y1="{H - 40 - (k / N) * (H - 80):.1f}" x2="50" '
        f'y2="{H - 40 - (k / N) * (H - 80):.1f}" stroke="#000"/>'
        f'<text x="42" y="{H - 36 - (k / N) * (H - 80):.1f}" font-size="9" '
        f'text-anchor="end">{k}</text>'
        for k in range(0, N + 1, 50)
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}">
<rect width="{W}" height="{H}" fill="#fff"/>
<text x="{W // 2}" y="20" font-size="14" text-anchor="middle" font-weight="600">
frust optimization: instances solved / {N} (probe set, 10s each)</text>
<line x1="50" y1="{H - 40}" x2="{W - 30}" y2="{H - 40}" stroke="#000"/>
<line x1="50" y1="40" x2="50" y2="{H - 40}" stroke="#000"/>
<line x1="50" y1="{H - 40 - (N / N) * (H - 80):.1f}" x2="{W - 30}"
 y2="{H - 40 - (N / N) * (H - 80):.1f}" stroke="#aaa" stroke-dasharray="3"/>
{yt}{bars}
<polyline points="{pts}" fill="none" stroke="#d62728" stroke-width="2"/>
{labels}
<text x="{W // 2}" y="{H - 6}" font-size="11" text-anchor="middle">iteration</text>
</svg>"""
    out = Path(__file__).resolve().parents[1] / "docs/dev_reports/frust_iterations.svg"
    out.write_text(svg)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
