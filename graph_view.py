#!/usr/bin/env python3
"""Render a small, source-backed wiki graph as a standalone SVG."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
from html import escape
from pathlib import Path

import brain


CARD_W = 256
CARD_H = 76
COL_GAP = 118
ROW_GAP = 80
PAD_X = 52
PAD_TOP = 147
KINDS = ("person", "project", "decision", "topic")
COLORS = {"person": "#c45f36", "project": "#346a93", "decision": "#7a5ba7", "topic": "#498274"}


def render(vault: Path, label: str) -> str:
    errors = brain.validate(vault)
    if errors:
        raise ValueError("Invalid vault:\n" + "\n".join(errors))
    pages = brain.read_pages(vault)
    by_kind: dict[str, list[dict]] = defaultdict(list)
    for page in pages:
        by_kind[page["meta"]["kind"]].append(page)
    kinds = [kind for kind in KINDS if kind in by_kind]
    kinds += sorted(set(by_kind) - set(kinds))
    width = max(650, PAD_X * 2 + len(kinds) * CARD_W + max(0, len(kinds) - 1) * COL_GAP)
    height = max(330, PAD_TOP + max((len(group) for group in by_kind.values()), default=0) * (CARD_H + ROW_GAP) + 35)
    positions = {}
    nodes = []
    for column, kind in enumerate(kinds):
        x = PAD_X + column * (CARD_W + COL_GAP)
        for row, page in enumerate(sorted(by_kind[kind], key=lambda item: item["meta"]["title"].casefold())):
            y = PAD_TOP + row * (CARD_H + ROW_GAP)
            positions[page["meta"]["id"]] = (x, y)
            nodes.append((page, kind, x, y))
    edges = [(page["meta"]["id"], rel["target"], rel["type"])
             for page in pages for rel in page["relations"] if rel["status"] == "active"]
    sources = len(brain.source_records(vault))
    source_word = "source" if sources == 1 else "sources"
    relationship_word = "relationship" if len(edges) == 1 else "relationships"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        f'<title id="title">{escape(label)} — current typed wiki graph</title>',
        f'<desc id="desc">{len(pages)} wiki pages, {len(edges)} active typed {relationship_word}, {sources} registered {source_word}.</desc>',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#798698"/></marker></defs>',
        f'<rect width="{width}" height="{height}" fill="#f7f9fc"/>',
        f'<text x="{PAD_X}" y="55" fill="#172338" font-size="26" font-weight="700" font-family="system-ui, sans-serif">{escape(label)}</text>',
        f'<text x="{PAD_X}" y="84" fill="#526176" font-size="14" font-family="system-ui, sans-serif">{len(pages)} pages  ·  {len(edges)} active {relationship_word}  ·  {sources} registered {source_word}</text>',
        f'<text x="{PAD_X}" y="112" fill="#738197" font-size="12" font-family="system-ui, sans-serif">Typed, source-backed edges from Markdown · {date.today().isoformat()}</text>',
    ]
    for origin, target, relation in edges:
        if origin not in positions or target not in positions:
            continue
        ox, oy = positions[origin]
        tx, ty = positions[target]
        if tx > ox:
            start = (ox + CARD_W, oy + CARD_H / 2)
            end = (tx - 9, ty + CARD_H / 2)
        elif tx < ox:
            start = (ox, oy + CARD_H / 2)
            end = (tx + CARD_W + 9, ty + CARD_H / 2)
        elif ty > oy:
            start = (ox + CARD_W / 2, oy + CARD_H)
            end = (tx + CARD_W / 2, ty - 9)
        else:
            start = (ox + CARD_W / 2, oy)
            end = (tx + CARD_W / 2, ty + CARD_H + 9)
        sx, sy = start
        ex, ey = end
        bend = (ex - sx) * 0.45
        parts.append(f'<path d="M {sx:.1f} {sy:.1f} C {sx+bend:.1f} {sy:.1f}, {ex-bend:.1f} {ey:.1f}, {ex:.1f} {ey:.1f}" fill="none" stroke="#8795a8" stroke-width="2" marker-end="url(#arrow)"/>')
        midx, midy = (sx + ex) / 2, (sy + ey) / 2
        parts.append(f'<text x="{midx:.1f}" y="{midy-11:.1f}" text-anchor="middle" fill="#617086" font-size="12" font-family="system-ui, sans-serif">{escape(relation.replace("_", " "))}</text>')
    for page, kind, x, y in nodes:
        title = page["meta"]["title"]
        if len(title) > 29:
            title = title[:28] + "…"
        color = COLORS.get(kind, "#5f6a7d")
        parts += [
            f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="12" fill="#ffffff" stroke="#dce3ec"/>',
            f'<rect x="{x}" y="{y}" width="5" height="{CARD_H}" rx="2" fill="{color}"/>',
            f'<text x="{x+20}" y="{y+28}" fill="{color}" font-size="11" font-weight="700" font-family="system-ui, sans-serif">{escape(kind.upper())}</text>',
            f'<text x="{x+20}" y="{y+54}" fill="#172338" font-size="16" font-weight="600" font-family="system-ui, sans-serif">{escape(title)}</text>',
        ]
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--label", default="Second Brain graph")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(args.vault.expanduser().resolve(), args.label), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
