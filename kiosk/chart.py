"""Server-side SVG bar chart: revenue per day. No JavaScript library needed.
Colours come from CSS variables (see style.css) so light and dark mode both work."""

from datetime import date
from math import ceil, floor, log10

from markupsafe import Markup, escape

DAYS_FULL = ["Jumatatu", "Jumanne", "Jumatano", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili"]
DAYS_SHORT = ["Jtt", "Jnn", "Jtn", "Alh", "Ijm", "Jmo", "Jpi"]
MONTHS = ["Jan", "Feb", "Mac", "Apr", "Mei", "Jun", "Jul", "Ago", "Sep", "Okt", "Nov", "Des"]

W, H = 340, 210
LEFT, RIGHT, TOP, BOTTOM = 40, 8, 26, 28
BAR_MAX = 24          # bars never fill their slot: leftover is air
RADIUS = 4            # rounded data end, square at the baseline


def day_label(iso):
    d = date.fromisoformat(iso)
    return f"{DAYS_FULL[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def compact(value):
    return f"{value / 1000:g}K" if value >= 1000 else f"{value:g}"


def nice_ticks(top_value):
    """Round axis ticks (0, 500, 1000, ...) that cover the largest value."""
    raw = top_value / 4
    magnitude = 10 ** floor(log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if raw <= m * magnitude)
    return [i * step for i in range(ceil(top_value / step) + 1)]


def bar_path(x, y, w, h):
    r = min(RADIUS, h)
    return (f"M{x:.1f},{y + h:.1f} L{x:.1f},{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
            f"L{x + w - r:.1f},{y:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} "
            f"L{x + w:.1f},{y + h:.1f} Z")


def sales_bars(days, title):
    """days: list of {'date','revenue','units'}. Returns SVG markup, or '' if no sales."""
    peak = max((d["revenue"] for d in days), default=0)
    if peak <= 0:
        return Markup("")

    ticks = nice_ticks(peak)
    y_max = ticks[-1]
    plot_w, plot_h = W - LEFT - RIGHT, H - TOP - BOTTOM
    slot = plot_w / len(days)
    bar_w = min(BAR_MAX, slot * 0.6)
    base_y = TOP + plot_h

    def y_of(v):
        return TOP + plot_h * (1 - v / y_max)

    parts = [f'<svg class="chart-svg" viewBox="0 0 {W} {H}" role="group" aria-label="{escape(title)}">']

    for tick in ticks:                                        # hairline grid + y labels
        y = y_of(tick)
        parts.append(f'<line class="grid" x1="{LEFT}" x2="{W - RIGHT}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text class="axis-text" x="{LEFT - 6}" y="{y + 4:.1f}" text-anchor="end">{compact(tick)}</text>')

    label_done = False
    for i, d in enumerate(days):
        slot_x = LEFT + i * slot
        x = slot_x + (slot - bar_w) / 2
        h = plot_h * d["revenue"] / y_max
        tip = f'{day_label(d["date"])}: KES {d["revenue"]:,}'
        weekday = DAYS_SHORT[date.fromisoformat(d["date"]).weekday()]

        parts.append(f'<g class="bar" tabindex="0" role="img" aria-label="{escape(tip)}" data-tip="{escape(tip)}">')
        parts.append(f'<rect class="hit" x="{slot_x:.1f}" y="{TOP}" width="{slot:.1f}" height="{plot_h}"/>')
        if h > 0:
            parts.append(f'<path class="mark" d="{bar_path(x, base_y - h, bar_w, h)}"/>')
        parts.append("</g>")
        if d["revenue"] == peak and not label_done:           # label the peak only, never every bar
            parts.append(f'<text class="value-text" x="{x + bar_w / 2:.1f}" y="{base_y - h - 6:.1f}" text-anchor="middle">{d["revenue"]:,}</text>')
            label_done = True
        parts.append(f'<text class="axis-text" x="{slot_x + slot / 2:.1f}" y="{H - 8}" text-anchor="middle">{weekday}</text>')

    parts.append("</svg>")
    return Markup("".join(parts))
