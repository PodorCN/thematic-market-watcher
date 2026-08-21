#!/usr/bin/env python3
"""Stage 4 -- render.py (render/ package)

Pure code, no LLM. Reads archive/<date>/analysis.json (and raw_data.json
for the ticker table/sparklines) and renders archive/<date>/report.html
via Jinja2. Deterministic and easy to debug: same inputs always produce
the same HTML.

Also copies the freshly rendered report to docs/index.html so GitHub
Pages (serving /docs) always shows the latest digest.

Usage:
    python render/render.py [--date YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

STAGE_DIR = Path(__file__).resolve().parent


def sparkline_svg(history: list[dict], width: int = 120, height: int = 32) -> str:
    """Tiny deterministic inline SVG sparkline from a list of {"close": float}."""
    closes = [point["close"] for point in history]
    if len(closes) < 2:
        return ""

    lo, hi = min(closes), max(closes)
    span = (hi - lo) or 1.0
    step = width / (len(closes) - 1)

    points = []
    for i, value in enumerate(closes):
        x = i * step
        y = height - ((value - lo) / span) * height
        points.append(f"{x:.1f},{y:.1f}")

    color = "#1f9d55" if closes[-1] >= closes[0] else "#d64545"
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'class="sparkline" role="img" aria-label="price trend">'
        f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" '
        f'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" />'
        f"</svg>"
    )


def build_ticker_rows(raw_data: dict) -> list[dict]:
    rows = []
    for symbol, info in raw_data.get("tickers", {}).items():
        if "error" in info:
            rows.append({"symbol": symbol, "error": info["error"]})
            continue
        rows.append(
            {
                "symbol": symbol,
                "name": info["name"],
                "last_close": info["last_close"],
                "currency": info["currency"],
                "change_pct": info["change_pct"],
                "sparkline": sparkline_svg(info["history"]),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    args = parser.parse_args()

    data_dir = REPO_ROOT / "archive" / args.date
    analysis = json.loads((data_dir / "analysis.json").read_text(encoding="utf-8"))
    raw_data = json.loads((data_dir / "raw_data.json").read_text(encoding="utf-8"))
    headlines = json.loads((data_dir / "headlines.json").read_text(encoding="utf-8"))

    env = Environment(loader=FileSystemLoader(str(STAGE_DIR)), autoescape=True)
    template = env.get_template("template.html.j2")

    html = template.render(
        report_date=args.date,
        analysis=analysis,
        tickers=build_ticker_rows(raw_data),
        headlines=headlines.get("headlines", []),
    )

    out_path = data_dir / "report.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path}")

    docs_dir = REPO_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out_path, docs_dir / "index.html")
    print(f"wrote {docs_dir / 'index.html'}")


if __name__ == "__main__":
    main()
