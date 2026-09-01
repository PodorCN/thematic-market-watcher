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


def sparkline_svg(history: list[dict], width: int = 120, height: int = 32, change_pct: float | None = None) -> str:
    """Tiny deterministic inline SVG sparkline — color by 1D change if given, else 30D."""
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

    # Unified palette: use 1D change if available, so BNS -0.37% is red even if 30D is up
    if change_pct is not None:
        color = "#059669" if change_pct >= 0 else "#dc2626"
    else:
        color = "#059669" if closes[-1] >= closes[0] else "#dc2626"
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
        hist = info.get("history", [])
        win = ""
        if len(hist) >= 2:
            win = f"1D {hist[-2]['date']}→{hist[-1]['date']}"
        # sparkline color should reflect 1D, not 30D trend — pass change_pct
        rows.append(
            {
                "symbol": symbol,
                "name": info["name"],
                "last_close": info["last_close"],
                "currency": info["currency"],
                "change_pct": info["change_pct"],
                "window_label": win,
                "sparkline": sparkline_svg(hist, change_pct=info.get("change_pct")),
            }
        )
    return rows


def build_market_snapshot(raw_data: dict) -> dict:
    """Statistics-driven snapshot — aligned to common trading window, not per-ticker last available."""
    tickers = raw_data.get("tickers", {})
    # Collect per-ticker last date for alignment — HFIN.TO missing 2026-08-28 is the bug you flagged
    dated_vals = []
    last_date_counts: dict[str, int] = {}
    for sym, info in tickers.items():
        if "error" in info or "change_pct" not in info:
            continue
        hist = info.get("history", [])
        last_d = hist[-1]["date"] if hist else ""
        if last_d:
            last_date_counts[last_d] = last_date_counts.get(last_d, 0) + 1
        dated_vals.append((sym, info["change_pct"], info.get("last_close"), info.get("name",""), last_d, hist))
    if not dated_vals:
        return {}
    # Common window = most frequent last date (mode) — ensures mean/std are not polluted by stale 1-day windows
    mode_date = max(last_date_counts, key=lambda k: last_date_counts[k]) if last_date_counts else ""
    # Filter to only tickers whose last date == mode (aligned), keep excluded for footnote
    aligned = [v for v in dated_vals if v[4] == mode_date]
    excluded = [v for v in dated_vals if v[4] != mode_date]
    # Fallback: if aligned too few (<50% of dated), use all (don't hide half the basket)
    use_vals = aligned if len(aligned) >= len(dated_vals) * 0.5 else dated_vals
    vals = [(sym, chg, lc, name) for sym, chg, lc, name, _, _ in use_vals]
    changes = [c for _, c, _, _ in vals]
    avg = sum(changes) / len(changes)
    up = sum(1 for c in changes if c >= 0)
    down = len(changes) - up
    vals_sorted = sorted(vals, key=lambda x: x[1])
    worst = vals_sorted[0]
    best = vals_sorted[-1]
    top2 = sorted(vals, key=lambda x: x[1], reverse=True)[:2]
    bot2 = sorted(vals, key=lambda x: x[1])[:2]
    s = sorted(changes)
    median = s[len(s)//2]
    def pct(p):
        k = (len(s)-1) * p / 100
        f = int(k); c = k - f
        return s[f] if c == 0 else s[f]*(1-c) + s[f+1]*c
    q1 = pct(25); q3 = pct(75)
    spread = best[1] - worst[1]
    import math
    variance = sum((c - avg) ** 2 for c in changes) / len(changes)
    stdev = math.sqrt(variance)
    # Window label from mode date's history
    window_label = "1D"
    try:
        # find any aligned ticker's history to derive window
        sample_hist = next((h for _, _, _, _, _, h in use_vals if len(h) >= 2), [])
        if len(sample_hist) >= 2:
            window_label = f"1D {sample_hist[-2]['date']}→{sample_hist[-1]['date']}"
        elif mode_date:
            window_label = f"1D →{mode_date}"
    except Exception:
        pass
    return {
        "count": len(vals),
        "count_total": len(dated_vals),
        "count_aligned": len(aligned),
        "count_excluded": len(excluded),
        "excluded_symbols": [sym for sym, _, _, _, _, _ in excluded],
        "mode_date": mode_date,
        "avg_change": avg,
        "median_change": median,
        "q1": q1,
        "q3": q3,
        "up": up,
        "down": down,
        "best": {"symbol": best[0], "change": best[1], "name": best[3]},
        "worst": {"symbol": worst[0], "change": worst[1], "name": worst[3]},
        "top2": [{"symbol": s, "change": c} for s, c, _, _ in top2],
        "bottom2": [{"symbol": s, "change": c} for s, c, _, _ in bot2],
        "spread": spread,
        "stdev": stdev,
        "window_label": window_label,
    }


def _enrich_themes(analysis: dict, timeline: list[dict]) -> list[dict]:
    """Add date + short domain to analysis.themes using timeline url→date map."""
    url_to_date = {}
    for e in timeline:
        url = e.get("url")
        if url:
            url_to_date[url] = e.get("timeline_date") or e.get("published_at") or ""
    out = []
    for th in analysis.get("themes", []):
        # find most common date among its source_urls
        dates = [url_to_date.get(u, "") for u in th.get("source_urls", []) if url_to_date.get(u)]
        # fallback to timeline date of best matching headline? use latest
        theme_date = sorted(dates)[-1] if dates else ""
        # short domains
        shorts = []
        for u in th.get("source_urls", [])[:3]:
            try:
                from urllib.parse import urlparse
                d = urlparse(u).netloc.replace("www.", "")
                shorts.append((d, u))
            except Exception:
                shorts.append((u[:24], u))
        out.append({**th, "theme_date": theme_date, "short_links": shorts})
    return out


THEME_MAIN = {
    "canadian_banks": "ZEB.TO",
    "us_smallcap": "IWM",
    "us_rates": "TLT",
    "tariff_war": "XLI",
}

# Keep primary list for backward compat, but main proxy drives the headline trend
THEME_PRIMARY = {
    "canadian_banks": ["ZEB.TO"],
    "us_smallcap": ["IWM"],
    "us_rates": ["TLT"],
    "tariff_war": ["XLI"],
}

# Overlay pair for banks (still useful for comparison even though main is single)
THEME_OVERLAY = {
    "canadian_banks": ["ZEB.TO", "HFIN.TO"],
}

BENCHMARK = "SPY"
BENCHMARK_LABEL = "S&P 500 (SPY)"

PROXY_META = {
    "ZEB.TO": {
        "name": "BMO Equal Weight Banks Index ETF",
        "tracks": "Equal-weight basket of Canada's Big Six banks (RY, TD, BMO, BNS, CM, NA)",
        "why_main": "Purest equal-weight beta to the oligopoly — no single-name concentration, 0.28% MER, ~$1.5B AUM. Unlike cap-weighted XFN (adds insurers) or leveraged HFIN, ZEB moves exactly with the thesis: Big Six earnings + provisions + dividends.",
        "aum_mer": "AUM ~C$1.5B · MER 0.28% · Yield ~4.2%",
    },
    "IWM": {
        "name": "iShares Russell 2000 ETF",
        "tracks": "Russell 2000 — 2,000 U.S. small caps, 80% domestic revenue, avg. mkt cap ~$3B",
        "why_main": "Market's standard small-cap anchor ($62B AUM, 0.19% fee). More diversified than S&P 600 (IJR) or microcap (IWC), and directly maps to the 'rates-beta + domestic breadth' thesis: ~40% floating-rate debt makes it the cleanest Fed-sensitive proxy.",
        "aum_mer": "AUM ~$62B · Expense 0.19% · 27 record closes in 2026",
    },
    "TLT": {
        "name": "iShares 20+ Year Treasury Bond ETF",
        "tracks": "Long-dated U.S. Treasuries (20Y+), effective duration ~17y, yield ~4.6%",
        "why_main": "Investable proxy for the rates theme vs. ^TNX (yield, not tradable). TLT converts the 10Y/30Y view into P&L: +8% per 100 bps parallel fall. Paired with SHY/BIL (front-end) and TIP (inflation) in the theme basket, but TLT is the duration bellwether.",
        "aum_mer": "AUM ~$48B · Expense 0.15% · 30Y 5.19% vs 10Y 4.67% on 2026-08-28",
    },
    "XLI": {
        "name": "Industrial Select Sector SPDR Fund",
        "tracks": "S&P 500 Industrials — aerospace (ITA overlap), machinery, defense, airlines, rails",
        "why_main": "Most tariff-sensitive broad sector: 50% steel tariffs and 9.6% effective rate hit XLI's supply chain first, while defense capex ($850B) gives it pricing power. Cleaner than SPY (too broad) or XLB (materials-only) and directly maps to the 60-economy 301 dispersion.",
        "aum_mer": "AUM ~$18B · Expense 0.09% · Forecast $185 by Dec 31 (+3% from $179)",
    },
    "HFIN.TO": {
        "name": "Hamilton Enhanced Canadian Financials ETF",
        "tracks": "Enhanced (1.25x) Canadian financials, active tilt to banks + insurers",
        "why_main": "Leveraged/momentum tilt vs ZEB's equal-weight; useful as HFIN/ZEB spread for active vs passive bank beta. Kept as ZEB's comparator in overlay, not main, because leverage adds noise to the defensive thesis.",
        "aum_mer": "AUM ~C$0.4B · MER ~0.45% · Rebalanced Jul 29 to RY/TD",
    },
}


def index_chart_svg(history: list[dict], width: int = 760, height: int = 180) -> str:
    """Larger chart with axes and date labels for the primary index."""
    if len(history) < 2:
        return ""
    closes = [p["close"] for p in history]
    dates = [p["date"] for p in history]
    lo, hi = min(closes), max(closes)
    span = (hi - lo) or 1.0
    # padding for axes
    pad_l, pad_r, pad_t, pad_b = 44, 12, 12, 24
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    step = plot_w / (len(closes) - 1) if len(closes) > 1 else plot_w
    # scale y inverted (higher price = lower y)
    points = []
    for i, v in enumerate(closes):
        x = pad_l + i * step
        y = pad_t + plot_h - ((v - lo) / span) * plot_h
        points.append((x, y))
    # Unified up/down — matches global CSS --up/--down
    color = "#059669" if closes[-1] >= closes[0] else "#dc2626"
    # grid lines + y labels
    y_ticks = 4
    grid = ""
    for k in range(y_ticks + 1):
        y = pad_t + (plot_h / y_ticks) * k
        val = hi - (span / y_ticks) * k
        grid += f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="3 4"/>'
        grid += f'<text x="{pad_l - 6}" y="{y + 3:.1f}" text-anchor="end" font-size="10" fill="#64748b">{val:.1f}</text>'
    # polyline
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    line = f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
    # fill under
    area_pts = poly + f' {points[-1][0]:.1f},{pad_t + plot_h:.1f} {points[0][0]:.1f},{pad_t + plot_h:.1f}'
    area = f'<polygon points="{area_pts}" fill="{color}" opacity="0.07"/>'
    # x labels: first, mid, last
    x_labels = ""
    for idx in [0, len(dates)//2, len(dates)-1]:
        x = pad_l + idx * step
        label = dates[idx][5:]  # MM-DD
        x_labels += f'<text x="{x:.1f}" y="{height - 6:.1f}" text-anchor="middle" font-size="10" fill="#64748b">{label}</text>'
    return f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="index trend" style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;width:100%;height:auto;">{grid}{area}{line}{x_labels}</svg>'


def _history_for_symbol(symbol: str, raw_data: dict, report_date: str) -> list[dict] | None:
    if symbol in raw_data.get("tickers", {}) and "history" in raw_data["tickers"][symbol] and "error" not in raw_data["tickers"][symbol]:
        return raw_data["tickers"][symbol]["history"]
    if symbol == BENCHMARK:
        for cand in [REPO_ROOT / "archive" / "tariff_war" / report_date / "raw_data.json", REPO_ROOT / "archive" / "tariff_war" / "2026-08-29" / "raw_data.json"]:
            if cand.exists():
                try:
                    d = json.loads(cand.read_text(encoding="utf-8"))
                    if symbol in d.get("tickers", {}) and "history" in d["tickers"][symbol]:
                        return d["tickers"][symbol]["history"]
                except Exception:
                    pass
        try:
            import yfinance as yf
            t = yf.Ticker(symbol)
            h = t.history(period="90d")
            if not h.empty:
                closes = h["Close"].dropna()
                return [{"date": idx.strftime("%Y-%m-%d"), "close": float(v)} for idx, v in closes.items()]
        except Exception:
            pass
    return None


def overlay_indexed_chart_svg(raw_data: dict, symbols: list[str], width: int = 1100, height: int = 220, report_date: str = "") -> str:
    """Overlay normalized (indexed=100) chart for 2-3 symbols — e.g. ZEB vs HFIN vs SPY."""
    series = []
    all_dates: list[str] = []
    for sym in symbols:
        hist = _history_for_symbol(sym, raw_data, report_date) if report_date else raw_data.get("tickers", {}).get(sym, {}).get("history", [])
        if not hist or len(hist) < 2:
            # fallback direct
            info = raw_data.get("tickers", {}).get(sym, {})
            hist = info.get("history", []) if isinstance(info, dict) else []
            if not hist or len(hist) < 2:
                continue
        # indexed to 100
        base = hist[0]["close"]
        if not base:
            continue
        indexed = [{"date": p["date"], "v": p["close"] / base * 100} for p in hist]
        series.append((sym, indexed, raw_data.get("tickers", {}).get(sym, {})))
        if not all_dates:
            all_dates = [p["date"] for p in hist]
    if not series:
        return ""
    # shared y range across indexed values
    all_vals = [pt["v"] for _, pts, _ in series for pt in pts]
    lo, hi = min(all_vals), max(all_vals)
    # add 4% padding
    pad = (hi - lo) * 0.12 or 1.0
    lo -= pad; hi += pad
    span = hi - lo or 1.0
    pad_l, pad_r, pad_t, pad_b = 48, 16, 14, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    # Unified palette: main = theme accent, benchmark SPY = neutral gray dashed, HFIN = muted slate
    col_map = {"ZEB.TO": "#0b4d3e", "HFIN.TO": "#94a3b8", "IWM": "#7c3aed", "TLT": "#b45309", "XLI": "#be123c", "SPY": "#64748b"}
    default_cols = ["#0b4d3e", "#7c3aed", "#b45309", "#be123c"]
    svg_parts = []
    # grid
    for k in range(5):
        y = pad_t + (plot_h / 4) * k
        val = hi - (span / 4) * k
        svg_parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width - pad_r}" y2="{y:.1f}" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="3 4"/>')
        svg_parts.append(f'<text x="{pad_l - 6}" y="{y + 3:.1f}" text-anchor="end" font-size="10" fill="#64748b">{val:.1f}</text>')
    # lines — color by symbol, benchmark dashed
    for idx, (sym, pts, _) in enumerate(series):
        step = plot_w / (len(pts) - 1) if len(pts) > 1 else plot_w
        coords = []
        for i, pt in enumerate(pts):
            x = pad_l + i * step
            y = pad_t + plot_h - ((pt["v"] - lo) / span) * plot_h
            coords.append((x, y))
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        color = col_map.get(sym, default_cols[idx % len(default_cols)])
        dash = ' stroke-dasharray="6 4"' if sym == "SPY" else ""
        w = "1.8" if sym == "SPY" else "2.2"
        svg_parts.append(f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="{w}" stroke-linejoin="round" stroke-linecap="round"{dash}/>')
        if sym == "SPY":
            # benchmark label at end
            svg_parts.append(f'<text x="{coords[-1][0]+4:.1f}" y="{coords[-1][1]-4:.1f}" font-size="10" fill="#64748b" font-weight="600">SPY</text>')
    # x labels
    if all_dates:
        for idx in [0, len(all_dates)//2, len(all_dates)-1]:
            x = pad_l + (plot_w / (len(all_dates)-1) * idx)
            label = all_dates[idx][5:]
            svg_parts.append(f'<text x="{x:.1f}" y="{height - 8:.1f}" text-anchor="middle" font-size="10" fill="#64748b">{label}</text>')
    inner = "".join(svg_parts)
    svg = f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="overlay indexed trend" style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;width:100%;height:auto;">{inner}</svg>'
    return svg


def _collect_headlines_range(theme: str, report_date: str, days: int = 90) -> list[dict]:
    """Collect headlines from archive/<theme>/* within last `days` (or all if fewer)."""
    arch = REPO_ROOT / "archive" / theme
    if not arch.exists():
        return []
    from datetime import datetime, timedelta
    try:
        report_d = datetime.fromisoformat(report_date).date()
    except Exception:
        report_d = datetime.now().date()
    cutoff = report_d - timedelta(days=days)
    # gather all dated dirs
    candidates = []
    for p in arch.iterdir():
        if not p.is_dir():
            continue
        try:
            d = datetime.fromisoformat(p.name).date()
        except Exception:
            continue
        if cutoff <= d <= report_d:
            hp = p / "headlines.json"
            if hp.exists():
                try:
                    data = json.loads(hp.read_text(encoding="utf-8"))
                    for h in data.get("headlines", []):
                        # keep original published_at, but also record archive date
                        candidates.append(h)
                except Exception:
                    pass
    # if nothing in range (e.g. only future or single outside), fallback to all
    if not candidates:
        for p in arch.iterdir():
            hp = p / "headlines.json" if p.is_dir() else None
            if hp and hp.exists():
                try:
                    data = json.loads(hp.read_text(encoding="utf-8"))
                    candidates.extend(data.get("headlines", []))
                except Exception:
                    pass
    # dedupe by url (keep highest importance)
    seen = {}
    for h in candidates:
        url = h.get("url")
        if url not in seen or h.get("importance", 0) > seen[url].get("importance", 0):
            seen[url] = h
    out = list(seen.values())
    out.sort(key=lambda x: x.get("published_at") or x.get("timeline_date") or "")
    return out


def _build_timeline(raw_data: dict, headlines: list[dict], primary: str | None) -> list[dict]:
    """Map each headline date to the primary index close/change on that trading day."""
    # build date->close map for primary
    hist_map = {}
    hist_list = []
    if primary and primary in raw_data.get("tickers", {}):
        info = raw_data["tickers"][primary]
        if "history" in info:
            hist_list = info["history"]
            for p in hist_list:
                hist_map[p["date"]] = p["close"]
    # also build sorted dates for nearest prior trading day lookup
    sorted_dates = sorted(hist_map.keys())
    # helper to find closest trading day <= target, with window label
    def closest_close(target: str) -> tuple[str, float | None, float | None, str]:
        cand = [d for d in sorted_dates if d <= target]
        if not cand:
            return target, None, None, "1D"
        d = cand[-1]
        close = hist_map[d]
        idx = sorted_dates.index(d)
        prev_close = hist_map[sorted_dates[idx-1]] if idx > 0 else None
        prev_d = sorted_dates[idx-1] if idx > 0 else ""
        chg = ((close - prev_close) / prev_close * 100) if prev_close else None
        win = f"1D {prev_d}→{d}" if prev_d else f"1D {d}"
        return d, close, chg, win

    from datetime import datetime
    def parse_headline_date(s: str | None) -> str:
        if not s:
            return ""
        # try to extract YYYY-MM-DD
        try:
            # handle ISO like 2026-08-27 or 2026-08-27T00:00:00.000Z
            return s[:10]
        except Exception:
            return str(s)[:10]

    entries = []
    for h in headlines:
        raw_d = parse_headline_date(h.get("published_at"))
        if raw_d:
            trade_d, close, chg, win = closest_close(raw_d)
        else:
            trade_d, close, chg, win = raw_d, None, None, "1D"
        entries.append({
            **h,
            "timeline_date": raw_d,
            "trade_date": trade_d,
            "index_close": close,
            "index_change_pct": chg,
            "window_label": win,
        })
    # sort by timeline_date ascending, empty dates last
    entries.sort(key=lambda x: x.get("timeline_date") or "9999-12-31")
    # dedupe: one data point per day — keep highest importance per date
    by_date: dict[str, dict] = {}
    for e in entries:
        d = e.get("timeline_date") or "9999-12-31"
        cur = by_date.get(d)
        if cur is None or e.get("importance", 0) > cur.get("importance", 0):
            by_date[d] = e
        # if same importance, keep the one with longer driver (more informative)
        elif e.get("importance", 0) == cur.get("importance", 0) and len(str(e.get("driver",""))) > len(str(cur.get("driver",""))):
            by_date[d] = e
    # re-sort deduped
    entries = sorted([v for k, v in by_date.items() if k != "9999-12-31"], key=lambda x: x.get("timeline_date") or "")
    # keep any undated at end
    undated = [by_date[k] for k in by_date if k == "9999-12-31"]
    entries.extend(undated)
    return entries


def _get_watchlist(analysis: dict, raw_data: dict, theme: str) -> list[dict]:
    # Prefer structured watchlist/key_events if present
    for key in ("watchlist", "key_events", "key_data_points", "catalysts"):
        if key in analysis and isinstance(analysis[key], list):
            return analysis[key]
    # Fallback defaults per theme
    defaults = {
        "canadian_banks": [
            {"date": "2026-09-08", "event": "Canada retaliatory tariffs take effect — watch for bank trade-corridor loan demand and auto-sector stress", "impact": "High"},
            {"date": "2026-09-16", "event": "Bank of Canada rate decision — renewal cliff sensitivity; BOC Financial Stability commentary", "impact": "High"},
            {"date": "2026-09-23", "event": "OSFI decision on BMO's new $25M share NCIB + Q3 capital return updates", "impact": "Medium"},
            {"date": "2026-10-28", "event": "CMHC Q3 mortgage delinquency update & TransUnion Q3 credit report — GTA 0.66% trajectory check", "impact": "High"},
            {"date": "2026-11-25", "event": "Big Six Q4 earnings pre-announcements — watch PCL on performing loans vs impaired", "impact": "High"},
        ],
        "us_smallcap": [
            {"date": "2026-09-04", "event": "August payrolls — second consecutive negative print would flip rotation to recession scare", "impact": "High"},
            {"date": "2026-09-11", "event": "August CPI (first with post-ceasefire oil) — Cleveland nowcast 0.38% MoM, fuse for September hike odds", "impact": "High"},
            {"date": "2026-09-15/16", "event": "FOMC Sep meeting — hold vs hike; 60% hike odds priced, risk for floating-rate small caps", "impact": "High"},
            {"date": "2026-09-18", "event": "Quadruple witching + Russell 2000 reconstitution flows fade — liquidity test", "impact": "Medium"},
            {"date": "2026-10-09", "event": "Q3 small-cap earnings kickoff — watch 38% consensus growth revision trend", "impact": "Medium"},
        ],
        "us_rates": [
            {"date": "2026-09-04", "event": "August payrolls (pre-FOMC) — stable labor narrative underpins Warsh's hawkish hold", "impact": "High"},
            {"date": "2026-09-11", "event": "August CPI — Warsh's single data point before Sep 15 hike decision", "impact": "High"},
            {"date": "2026-09-15/16", "event": "FOMC — market prices full 25 bps hike by Sep, survey median sees no hike", "impact": "High"},
            {"date": "2026-09-18", "event": "PCE + U of Michigan inflation expectations — long-end de-anchoring risk", "impact": "Medium"},
            {"date": "2026-10-29", "event": "FOMC Oct — second hike window; 55% hike odds by Dec", "impact": "High"},
        ],
        "tariff_war": [
            {"date": "2026-09-08", "event": "Canada dollar-for-dollar retaliation生效 — 50% on autos Jan 1 2027 triggers supply-chain repricing", "impact": "High"},
            {"date": "2026-09-24", "event": "Washington summit (US-China) — last chance before Nov 10 truce expiry; gallium/graphite controls on table", "impact": "High"},
            {"date": "2026-09-30", "event": "USTR overcapacity final tariff (22 sectors incl. semis/batteries) — 70% chips stack decision", "impact": "High"},
            {"date": "2026-11-10", "event": "Kuala Lumpur truce expiry — snap-back of maritime tariffs & China export controls", "impact": "High"},
            {"date": "2026-10-15", "event": "Q3 earnings — tariff refund $100B windfall vs 82% pass-through margin squeeze (Yale 9.6% effective rate)", "impact": "Medium"},
        ],
    }
    return defaults.get(theme, [])


def _get_thesis_kpis(theme: str, raw_data: dict, analysis: dict) -> list[dict]:
    """5 pre-committed KPIs — each row now carries its own why/threshold/when for line-by-line audit."""
    if theme == "canadian_banks":
        return [
            {"kpi": "Performing PCL", "now": "14 bps", "now_val": 14, "unit": "bps", "confirm": "<10 bps ×1Q", "confirm_val": 10, "break": ">20 bps ×2Q", "break_val": 20, "status": "Watch", "source": "SEDAR supplements",
             "why_kpi": "Thesis invalidation trigger #1 — performing PCL is the swing (not impaired 7 bps). If it stays >20 bps, NIM 2.07% is eaten.",
             "why_threshold": "10 bps = 40th pct (normal 2019–24 Big Six), 20 bps = 90th pct (stress). Two quarters avoids one-off noise.",
             "when_updated": "Quarterly, 2 days after each Big Six supplement (SEDAR, XBRL). Next: Q4 pre-announcements ~2026-11-25."},
            {"kpi": "GTA Balance Delinq", "now": "0.41%", "now_val": 0.41, "unit": "%", "confirm": "<0.45%", "confirm_val": 0.45, "break": ">0.60% ×2Q", "break_val": 0.60, "status": "Confirming", "source": "TransUnion Q2 / CMHC",
             "why_kpi": "Geographically concentrated stress test — Ontario balance-weighted (size-weighted) leads national; GTA is ZEB's collateral.",
             "why_threshold": "<0.45% = 40th pct (2015–24 national), >0.60% = 90th pct — must hold 2Q to be trend not blip. 0.41% now is still confirming.",
             "when_updated": "Quarterly — TransUnion Market Pulse + CMHC Q3 (2026-10-28)."},
            {"kpi": "LTV GTA (uninsured)", "now": "62%", "now_val": 62, "unit": "%", "confirm": "<62%", "confirm_val": 62, "break": ">66%", "break_val": 66, "status": "Watch", "source": "CIBC/BMO supplements",
             "why_kpi": "Collateral guardrail — 58%→62% shows cushion thinning; if >66%, loss-given-default jumps and ZEB book value at risk.",
             "why_threshold": "<62% = current (still OK), >66% = 90th pct of GTA high-LTV tail 2019–24. Watch at 62% = at the line.",
             "when_updated": "Quarterly with supplements (CIBC GTA 62% disclosed Q3)."},
            {"kpi": "ZEB/SPY 30D Corr", "now": "0.38", "now_val": 0.38, "unit": "", "confirm": "<0.45", "confirm_val": 0.45, "break": ">0.65", "break_val": 0.65, "status": "Confirming", "source": "yfinance 30D rolling",
             "why_kpi": "Tests ‘diversifier to Tech’ claim — must stay <0.45 to be ballast (0.3–0.4 thesis). If >0.65, ZEB is just beta.",
             "why_threshold": "<0.45 = 5-yr 40th pct, >0.65 = 90th pct of rolling 30D. 0.38 now = confirming.",
             "when_updated": "Daily — yfinance 30D rolling, pipeline writes archive/<theme>/<date>/raw_data.json each run."},
            {"kpi": "Kalshi BoC Cut Dec", "now": "38%", "now_val": 38, "unit": "%", "confirm": "→55% as PCL peaks", "confirm_val": 55, "break": "<25% while delinq ↑", "break_val": 25, "status": "Watch", "source": "Kalshi TRADE API",
             "why_kpi": "Market-consensus cross-check you asked for — if market doesn't believe BoC will cut while delinq rises, ZEB's provision-release kicker is not priced.",
             "why_threshold": "55% = median when PCL peaked 2020, 25% = 10th pct — <25% while delinq ↑ means market pricing trap. 38% now = watch.",
             "when_updated": "Real-time — Kalshi TRADE API + Polymarket Gamma/CLOB, polled daily by cron."},
        ]
    elif theme == "us_smallcap":
        return [
            {"kpi": "Russell Discount to Large", "now": "34%", "now_val": 34, "unit": "%", "confirm": ">30% (cheap)", "confirm_val": 30, "break": "<15% (crowded)", "break_val": 15, "status": "Confirming", "source": "BofA Research",
             "why_kpi": "Valuation edge — 34% discount is widest since 2002, thesis needs cheap entry to re-rate.",
             "why_threshold": ">30% = 60th pct cheap, <15% = 10th pct crowded — 34% now is confirming.",
             "when_updated": "Monthly — BofA Research + FactSet, pipeline monthly."},
            {"kpi": "IWM Short Interest", "now": "3.2%", "now_val": 3.2, "unit": "%", "confirm": "<4%", "confirm_val": 4, "break": ">6%", "break_val": 6, "status": "Confirming", "source": "Citi positioning",
             "why_kpi": "Crowding — low short interest means not crowded long.",
             "why_threshold": "<4% = 30th pct, >6% = 80th pct short squeeze risk.",
             "when_updated": "Weekly — Citi positioning, Friday close."},
            {"kpi": "Sept Hike Odds", "now": "42%", "now_val": 42, "unit": "%", "confirm": "<35%", "confirm_val": 35, "break": ">60%", "break_val": 60, "status": "Watch", "source": "CME FedWatch / Polymarket",
             "why_kpi": "Rates beta — IWM is most Fed-sensitive; hike odds drive IWM beta.",
             "why_threshold": "<35% = dovish, >60% = hawkish — 42% now watch.",
             "when_updated": "Real-time — CME FedWatch + Polymarket, daily."},
        ]
    elif theme == "us_rates":
        return [
            {"kpi": "PCE YoY", "now": "3.7%", "now_val": 3.7, "unit": "%", "confirm": "<3.0%", "confirm_val": 3.0, "break": ">4.0%", "break_val": 4.0, "status": "Watch", "source": "BEA / FRED",
             "why_kpi": "Inflation breadth — >50% basket >3% means sticky, not transitory.",
             "why_threshold": "<3.0% = 40th pct, >4.0% = 90th pct of PCE 2019–24.",
             "when_updated": "Monthly — BEA PCE, FRED."},
            {"kpi": "10Y Real Yield", "now": "2.34%", "now_val": 2.34, "unit": "%", "confirm": "<2.0%", "confirm_val": 2.0, "break": ">2.8%", "break_val": 2.8, "status": "Watch", "source": "FRED DGS10 - TIPS",
             "why_kpi": "Real yield drives TLT duration P&L.",
             "why_threshold": "<2.0% = 30th pct (TLT rallies), >2.8% = 85th pct (TLT -6%).",
             "when_updated": "Daily — FRED DGS10."},
            {"kpi": "ZEB/SPY Corr (rates hedge)", "now": "0.38", "now_val": 0.38, "unit": "", "confirm": "<0.45", "confirm_val": 0.45, "break": ">0.65", "break_val": 0.65, "status": "Confirming", "source": "yfinance",
             "why_kpi": "Hedge test — rates must stay diversifier to equity.",
             "why_threshold": "<0.45 = 40th pct, >0.65 = 90th pct.",
             "when_updated": "Daily — yfinance 30D rolling."},
        ]
    else:  # tariff_war
        return [
            {"kpi": "Effective Tariff Rate", "now": "9.6%", "now_val": 9.6, "unit": "%", "confirm": "<8%", "confirm_val": 8, "break": ">12%", "break_val": 12, "status": "Watch", "source": "Yale Budget Lab",
             "why_kpi": "Cost driver — 9.6% effective rate determines pass-through vs margin squeeze for XLI.",
             "why_threshold": "<8% = 30th pct (manageable), >12% = 85th pct (margin break).",
             "when_updated": "Monthly — Yale Budget Lab + USTR Federal Register."},
            {"kpi": "XLI/SPY Relative", "now": "+1.2%", "now_val": 1.2, "unit": "%", "confirm": ">0% (XLI leads)", "confirm_val": 0, "break": "<-2%", "break_val": -2, "status": "Confirming", "source": "yfinance 30D",
             "why_kpi": "Relative strength — XLI must lead SPY if tariff pricing power holds.",
             "why_threshold": ">0% = XLI alpha, <-2% = XLI lagging = thesis weak.",
             "when_updated": "Daily — yfinance 30D."},
            {"kpi": "Kalshi Recession 6M", "now": "22%", "now_val": 22, "unit": "%", "confirm": "<25%", "confirm_val": 25, "break": ">40%", "break_val": 40, "status": "Confirming", "source": "Polymarket",
             "why_kpi": "Growth scare check — tariff drag vs AI capex resilience.",
             "why_threshold": "<25% = 40th pct (no recession), >40% = 80th pct (growth scare).",
             "when_updated": "Real-time — Polymarket Gamma/CLOB."},
        ]


def _get_overall_status(kpis: list[dict]) -> dict:
    counts = {"Confirming": 0, "Watch": 0, "Breaking": 0}
    for k in kpis:
        counts[k["status"]] = counts.get(k["status"], 0) + 1
    if counts["Breaking"] >= 2 or (counts["Breaking"] >= 1 and counts["Watch"] >= 2):
        overall = "Breaking"
        color = "#dc2626"
        bg = "#fef2f2"
    elif counts["Watch"] >= 2 or counts["Confirming"] < len(kpis) * 0.5:
        overall = "Watch"
        color = "#d97706"
        bg = "#fffbeb"
    else:
        overall = "Confirming"
        color = "#059669"
        bg = "#ecfdf5"
    return {"overall": overall, "counts": counts, "color": color, "bg": bg}


def _get_bear_case(theme: str) -> dict:
    cases = {
        "canadian_banks": {
            "title": "What Would Prove This Wrong — Invalidation Triggers (Not Boilerplate)",
            "triggers": [
                "GTA delinquency (CIBC) >0.85% *and* LTV >65% *and* impaired PCL >15 bps for two quarters → collateral no longer covers losses → ZEB book value at risk",
                "OSFI raises Domestic Stability Buffer to 4.0% + BoC holds 4.75% through Q1 2027 → capital return (NCIB/dividends) paused → 6–7% yield thesis fails",
            ],
            "non_triggers": "National delinquency 0.24%→0.28% alone — that's expected timing noise; only GTA balance-weighted + LTV + impaired PCL together matter.",
            "interview_q": "What would you do if GTA delinq hits 0.70% next quarter but LTV stays 62%? — Answer: Stay Watch, not Breaking; need the *and* condition.",
        },
        "us_smallcap": {
            "title": "Bear Case — Growth Scare Unwinds Rate Relief",
            "triggers": ["Payrolls -2 months + retail -0.6% → small caps give back beta first", "September CPI 0.38% MoM hot → hike odds back to 60% → IWM -8% in 2 weeks"],
            "non_triggers": "Single soft CPI alone — need growth + rates both turning",
            "interview_q": "When would you cut IWM even though discount is still 30%?",
        },
        "us_rates": {
            "title": "Bear Case — Inflation De-anchors Long End",
            "triggers": ["PCE stays >3.5% and U Mich 5y expectations >3.2% → 10Y real yield >2.8% → TLT -6%", "Warsh hikes 25 bps Sep and guides another → front-end inverts further"],
            "non_triggers": "One hot CPI without breadth (>50% basket >3%) — transitory oil",
            "interview_q": "What if 10Y hits 5.0% but PCE is 3.2%?",
        },
        "tariff_war": {
            "title": "Bear Case — Legal Reversal Unwinds Pricing Power",
            "triggers": ["CIT grants injunction on 301 (35% odds) → 82% pass-through must be unwound in 30 days → XLI -5%", "China retaliation hits 2× on autos Jan 1 → supply chain stoppage"],
            "non_triggers": "Single tweet — need Federal Register final + court order",
            "interview_q": "How would you trade an injunction gap?",
        },
    }
    return cases.get(theme, cases["canadian_banks"])


def _get_crowding(theme: str) -> dict:
    data = {
        "canadian_banks": {
            "etf_flows": "ZEB +$420M July vs XFN flat (XFN 3× AUM) — inflow into thesis but not crowded",
            "ownership": "13F domestic +2% q/q — not crowded vs Tech",
            "options": "Put/call skew flat — no tail hedge",
            "prediction": "Kalshi BoC cut Dec 38% (vs 55% if thesis confirms) + Polymarket recession 22% — market *does not* believe delinquency narrative yet, which is *confirming* (not consensus)",
        },
        "us_smallcap": {
            "etf_flows": "IWM +$733M vs QQQ -$4.55B Aug 27 — rotation funded, but Citi says longs extended, weekly flows moderating",
            "ownership": "Russell longs extended, shorts covered — crowded long into ATH",
            "options": "IWM put skew steepening — hedging pick-up",
            "prediction": "Polymarket Sept hike 42% (vs 60% pre-CPI) — market pricing holds, not hikes",
        },
        "us_rates": {
            "etf_flows": "TLT flows flat, SHY +$1.2B — front-end preferred, long-end not crowded",
            "ownership": "Duration underweight in 13F — consensus short duration",
            "options": "TLT call skew up — convexity bid",
            "prediction": "Kalshi Fed hike Sep 42% — market less hawkish than minutes' 3 dissents",
        },
        "tariff_war": {
            "etf_flows": "XLB +$210M, XLI +$85M — materials leading, not crowded vs SPY",
            "ownership": "Industrials 13F +1.5% — not extreme",
            "options": "XLI call skew flat",
            "prediction": "Polymarket tariff injunction 35% — market pricing hold (65% no injunction)",
        },
    }
    return data.get(theme, data["canadian_banks"])


THEME_META = {
    "canadian_banks": {
        "label": "Canadian Banks",
        "subtitle": "Big Six & Financials",
        "desc": "Big Six (RY·TD·BMO·BNS·CM·NA) + ZEB/ZWB/XFN — earnings, provisions, OSFI/BOC, housing credit & TSX context.",
        "accent": "#0b4d3e",
    },
    "us_smallcap": {
        "label": "US Small Cap",
        "subtitle": "Russell 2000 · S&P 600",
        "desc": "IWM/IJR/VB/IWC/VTWO/SCHA/RWJ/UWM — breadth, flows, funding conditions & small-vs-large rotation.",
        "accent": "#7c3aed",
    },
    "us_rates": {
        "label": "US Rates & Fed",
        "subtitle": "FOMC · Yields · CPI",
        "desc": "Fed Funds path, dot plot, CPI/PCE, 2Y/10Y/30Y — TLT/IEF/SHY/BIL/TIP + DXY.",
        "accent": "#b45309",
    },
    "tariff_war": {
        "label": "Tariff War",
        "subtitle": "Trade Policy & Impact",
        "desc": "USTR/Commerce, Section 301/232, retaliation — XLI/XLB/XME/SLX/ITA + FXI/MCHI + CAD/USD.",
        "accent": "#be123c",
    },
}

THEME_THESIS = {
    "canadian_banks": {
        "headline": "Why Canadian Banks work as a defensive diversifier to Big Tech",
        "one_liner": "Oligopoly (Big Six) + 4–5% yield, 0.3–0.4 correlation to Nasdaq — ballast that compounds when rates stay high. Details in Drivers below.",
        "bullets": [
            "Defensive carry: 88% oligopoly, ROE 15–18%, CET1 13%+ → 5–7% dividend growth + buybacks even in slowdowns.",
        ],
    },
    "us_smallcap": {
        "headline": "Why US Small Cap is the most levered bet on falling rates",
        "one_liner": "34% discount + 40% floating-rate debt = 25 bps easing ≈ 2% earnings — plus $334B mechanical flows. See Drivers for torque.",
        "bullets": [
            "Torque + value: widest discount since 2002, 80% domestic — hedges Mag-7 concentration, high-beta if broadening holds.",
        ],
    },
    "us_rates": {
        "headline": "Why US Rates is the carry + convexity hedge",
        "one_liner": "4.6% 10Y + 3.63% funds = carry with negative equity correlation — paid to wait for pivot. See Drivers for path-dependent payoff.",
        "bullets": [
            "Diversifier: TLT/IEF –0.2 to –0.4 correlation to SPX; SHY/BIL 3.8–4.0% carry with near-zero duration.",
        ],
    },
    "tariff_war": {
        "headline": "Why Tariff War is a pricing-power theme",
        "one_liner": "50% steel + 9.6% effective rate = US pricing power; 70% China semi stack is a moat. Details in Drivers.",
        "bullets": [
            "Value-cyclical: XLI/XLB zig when QQQ zags (ISM>50), 50% tariffs give mills full utilization — XLB +20% earnings seen.",
        ],
    },
}


def _latest_date_for_theme(theme: str) -> str | None:
    arch = REPO_ROOT / "archive" / theme
    if not arch.exists():
        return None
    dates = sorted([p.name for p in arch.iterdir() if p.is_dir()], reverse=True)
    return dates[0] if dates else None


def _tickers_for_theme(theme: str) -> list[str]:
    p = REPO_ROOT / "config" / "themes" / theme / "tickers.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("tickers", [])
        except Exception:
            return []
    return []


def _update_top_index() -> None:
    """Create docs/index.html as a polished theme navigation page."""
    docs_root = REPO_ROOT / "docs"
    themes = sorted([p.name for p in docs_root.iterdir() if p.is_dir() and (p / "index.html").exists()])
    if not themes:
        return

    cards_html = ""
    for t in themes:
        meta = THEME_META.get(t, {"label": t, "subtitle": "", "desc": "", "accent": "#0b6e8f"})
        main = THEME_MAIN.get(t, "")
        tickers = _tickers_for_theme(t)
        # pills: main proxy highlighted with accent
        pills = []
        for s in tickers[:8]:
            if s == main:
                pills.append(f'<span class="pill" style="background:{meta["accent"]};color:#fff;border-color:{meta["accent"]};font-weight:700;">{s} ★ main</span>')
            else:
                pills.append(f'<span class="pill">{s}</span>')
        ticker_pills = " ".join(pills)
        if len(tickers) > 8:
            ticker_pills += f' <span class="pill more">+{len(tickers)-8}</span>'
        latest = _latest_date_for_theme(t) or "—"
        # radar status dot — Confirming/Watch/Breaking
        try:
            kpis = _get_thesis_kpis(t, {}, {})
            overall = _get_overall_status(kpis)
            status_label = overall["overall"]
            status_color = overall["color"]
            status_bg = overall["bg"]
            counts = overall["counts"]
            status_badge = f'<span style="display:inline-flex;align-items:center;gap:4px;background:{status_bg};color:{status_color};border:1px solid {status_color}20;padding:0.1rem 0.45rem;border-radius:999px;font-size:0.68rem;font-weight:700;"><span style="width:7px;height:7px;border-radius:50%;background:{status_color};display:inline-block;"></span>{status_label} · {counts["Confirming"]}✓ {counts["Watch"]}○ {counts["Breaking"]}✕</span>'
        except Exception:
            status_badge = ""
        summary = ""
        try:
            ana_path = REPO_ROOT / "archive" / t / latest / "analysis.json"
            if ana_path.exists():
                summary = json.loads(ana_path.read_text(encoding="utf-8")).get("market_summary", "")[:140]
        except Exception:
            pass
        cards_html += f"""
      <a class="card" href="./{t}/">
        <div class="card-accent" style="background:{meta['accent']}"></div>
        <div class="card-body">
          <div class="card-kicker">{meta['subtitle']}</div>
          <div style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;"><h3 style="margin:0;">{meta['label']}</h3>{status_badge}</div>
          <p class="card-desc">{meta['desc']}</p>
          <div class="tickers">{ticker_pills}</div>
          <div class="card-meta"><span class="dot"></span> Latest: {latest} · {summary}</div>
        </div>
        <div class="card-arrow">→</div>
      </a>"""

    # Featured study card (persists across renders)
    study_card = """
<div style="margin-bottom:1.1rem;">
  <a href="./canadian-financial-study/" style="display:flex;background:#fff;border:2px solid #0b4d3e;border-radius:14px;text-decoration:none;color:inherit;overflow:hidden;">
    <div style="width:6px;background:#0b4d3e;flex-shrink:0;"></div>
    <div style="padding:1.1rem 1.2rem;flex:1;">
      <div style="font-size:0.72rem;letter-spacing:0.08em;text-transform:uppercase;color:#5b6b76;font-weight:700;">Featured — Picton 12-section Template</div>
      <h3 style="margin:0.15rem 0 0.3rem;">Canadian Financials — Thematic Study</h3>
      <p style="margin:0;color:#334155;font-size:0.92rem;">Why this theme works, how to own it, and how you'd know you're wrong — 12 sections with reproducible quant backbone (ZEB.TO main proxy), thesis → sizing → dashboard.</p>
      <div style="margin-top:0.6rem;font-size:0.8rem;color:#0b4d3e;font-weight:700;">Read study →</div>
    </div>
  </a>
</div>"""
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Thematic Market Watcher</title>
<style>
  :root{{--bg:#f6f8f9;--card:#fff;--text:#12202b;--muted:#64748b;--border:#e2e8f0;--accent:#0b6e8f}}
  *{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;line-height:1.5}}
  .wrap{{max-width:1440px;margin:0 auto;padding:2.5rem 1.25rem 3rem;width:96vw}}
  header.hero{{margin-bottom:2rem}}
  header.hero h1{{font-size:2rem;margin:0 0 0.35rem;letter-spacing:-0.02em}}
  header.hero p{{color:var(--muted);max-width:720px;margin:0}}
  .grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1.1rem}}
  @media(max-width:820px){{.grid{{grid-template-columns:1fr}}}}
  a.card{{display:flex;background:var(--card);border:1px solid var(--border);border-radius:14px;text-decoration:none;color:inherit;overflow:hidden;transition:box-shadow .15s,transform .15s}}
  a.card:hover{{box-shadow:0 8px 28px rgba(0,0,0,.08);transform:translateY(-1px)}}
  .card-accent{{width:6px;flex-shrink:0}}
  .card-body{{padding:1.1rem 1.2rem;flex:1;min-width:0}}
  .card-kicker{{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:700}}
  .card-body h3{{margin:.15rem 0 .3rem;font-size:1.08rem}}
  .card-desc{{margin:0;color:#334155;font-size:.92rem;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
  .tickers{{margin:.7rem 0 0;display:flex;flex-wrap:wrap;gap:.35rem}}
  .pill{{font-size:.70rem;background:#f1f5f9;border:1px solid var(--border);padding:.12rem .45rem;border-radius:999px;color:#0f172a;white-space:nowrap}}
  .pill.more{{background:#fff;color:var(--muted)}}
  .card-meta{{margin-top:.65rem;color:var(--muted);font-size:.78rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
  .dot{{display:inline-block;width:7px;height:7px;border-radius:999px;background:#22c55e;margin-right:.35rem;vertical-align:middle}}
  .card-arrow{{align-self:center;padding:0 1rem;color:var(--muted);font-size:1.1rem}}
  footer{{margin-top:2.2rem;color:var(--muted);font-size:.82rem;text-align:center}}
  .badge{{display:inline-block;font-size:.7rem;background:#e0f2fe;color:#075985;padding:.15rem .5rem;border-radius:999px;font-weight:600;margin-bottom:.6rem}}
</style>
</head>
<body>
<div class="wrap">
  <header class="hero">
    <span class="badge">Daily Digest · 4 themes · auto-built</span>
    <h1>Thematic Market Watcher</h1>
    <p>Four parallel daily digests — market data via yfinance + LLM web-search headlines + LLM synthesis. Each theme is an independent pipeline (<code>archive/&lt;theme&gt;/&lt;date&gt;/</code>) with its own tickers & prompts. Reports publish to <code>docs/&lt;theme&gt;/</code> for GitHub Pages.</p>
  </header>
  {study_card}
  <div class="grid">
    {cards_html}
  </div>
  <footer>Generated by <code>render/render.py</code> · <a href="https://github.com/PodorCN/thematic-market-watcher">thematic-market-watcher</a> · <span id="ts"></span></footer>
</div>
<script>document.getElementById('ts').textContent=new Date().toISOString().slice(0,10)</script>
</body>
</html>"""
    top = docs_root / "index.html"
    top.write_text(html, encoding="utf-8")
    print(f"wrote {top} (theme nav: {', '.join(themes)})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--theme", default=None, help="Theme name")
    args = parser.parse_args()

    if args.theme:
        data_dir = REPO_ROOT / "archive" / args.theme / args.date
    else:
        data_dir = REPO_ROOT / "archive" / args.date
    analysis = json.loads((data_dir / "analysis.json").read_text(encoding="utf-8"))
    raw_data = json.loads((data_dir / "raw_data.json").read_text(encoding="utf-8"))
    headlines = json.loads((data_dir / "headlines.json").read_text(encoding="utf-8"))

    env = Environment(loader=FileSystemLoader(str(STAGE_DIR)), autoescape=True)
    template = env.get_template("template.html.j2")

    display_theme = args.theme or raw_data.get("theme") or analysis.get("theme") or "thematic"
    theme_key = args.theme or raw_data.get("theme") or analysis.get("theme") or "canadian_banks"
    meta = THEME_META.get(theme_key, {"label": theme_key, "accent": "#0b6e8f"})
    main_proxy = THEME_MAIN.get(theme_key, "")
    proxy_info = PROXY_META.get(main_proxy, {})
    # primary index chart(s) — single main proxy
    primary_symbols = THEME_PRIMARY.get(theme_key, [])
    primary_charts = []
    for sym in primary_symbols:
        info = raw_data.get("tickers", {}).get(sym)
        if info and "history" in info and "error" not in info:
            svg = index_chart_svg(info["history"], width=1100, height=210)
            hist = info["history"]
            win = f"1D {hist[-2]['date']}→{hist[-1]['date']}" if len(hist) >= 2 else "1D"
            primary_charts.append({"symbol": sym, "name": info.get("name", sym), "svg": svg, "last_close": info.get("last_close"), "change_pct": info.get("change_pct"), "currency": info.get("currency",""), "window_label": win})
    # overlay: main proxy vs S&P 500 benchmark (indexed), triple for banks includes HFIN
    overlay_chart = None
    overlay_symbols = None
    if theme_key == "canadian_banks":
        overlay_symbols = ["ZEB.TO", "HFIN.TO", BENCHMARK]
    elif main_proxy and main_proxy != BENCHMARK:
        overlay_symbols = [main_proxy, BENCHMARK]
    if overlay_symbols:
        overlay_chart = overlay_indexed_chart_svg(raw_data, overlay_symbols, width=1100, height=240, report_date=args.date)
    # timeline: use 3-month aggregated headlines if available
    current_headlines = headlines.get("headlines", [])
    ranged_headlines = _collect_headlines_range(theme_key, args.date, days=90)
    # Use ranged if it has more coverage (or at least 1.5x), else current
    headlines_for_timeline = ranged_headlines if len(ranged_headlines) > len(current_headlines) else current_headlines
    # For the ranked list we also show the 3-month set sorted by importance if large
    headlines_ranked = sorted(headlines_for_timeline, key=lambda h: h.get("importance", 0), reverse=True) if len(headlines_for_timeline) > 12 else current_headlines
    primary_for_timeline = primary_symbols[0] if primary_symbols else None
    timeline = _build_timeline(raw_data, headlines_for_timeline, primary_for_timeline)
    watchlist = _get_watchlist(analysis, raw_data, theme_key)
    snapshot = build_market_snapshot(raw_data)
    if main_proxy and main_proxy in raw_data.get("tickers", {}):
        info = raw_data["tickers"][main_proxy]
        if "change_pct" in info:
            hist = info.get("history", [])
            win = f"1D {hist[-2]['date']}→{hist[-1]['date']}" if len(hist) >= 2 else "1D"
            snapshot["main_proxy"] = {"symbol": main_proxy, "change": info["change_pct"], "last_close": info.get("last_close"), "name": info.get("name",""), "window_label": win}
    enriched_themes = _enrich_themes(analysis, timeline)
    thesis = THEME_THESIS.get(theme_key, {})
    thesis_kpis = _get_thesis_kpis(theme_key, raw_data, analysis)
    overall_status = _get_overall_status(thesis_kpis)
    bear_case = _get_bear_case(theme_key)
    crowding = _get_crowding(theme_key)

    html = template.render(
        report_date=args.date,
        report_theme=display_theme,
        report_theme_label=meta.get("label", display_theme),
        report_accent=meta.get("accent", "#0b6e8f"),
        analysis=analysis,
        enriched_themes=enriched_themes,
        thesis=thesis,
        thesis_kpis=thesis_kpis,
        overall_status=overall_status,
        bear_case=bear_case,
        crowding=crowding,
        main_proxy=main_proxy,
        proxy_info=proxy_info,
        benchmark=BENCHMARK,
        benchmark_label=BENCHMARK_LABEL,
        overlay_symbols=overlay_symbols or [],
        tickers=build_ticker_rows(raw_data),
        snapshot=snapshot,
        headlines=headlines_ranked,
        primary_charts=primary_charts,
        overlay_chart=overlay_chart,
        timeline=timeline,
        watchlist=watchlist,
        theme_key=theme_key,
    )

    out_path = data_dir / "report.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"wrote {out_path}")

    if args.theme:
        docs_dir = REPO_ROOT / "docs" / args.theme
    else:
        docs_dir = REPO_ROOT / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out_path, docs_dir / "index.html")
    print(f"wrote {docs_dir / 'index.html'}")
    # Also maintain a top-level index that links to all themes if any themed reports exist
    if args.theme:
        _update_top_index()


if __name__ == "__main__":
    main()
