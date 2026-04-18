#!/usr/bin/env python3
"""Render an exported Ghost strategy DAG as a self-contained HTML file.

Examples:

    python tools/render_strategy_graph.py --dag strategy.json --output strategy.html

This renderer only reads the strategy DAG JSON. It does not read or visualize
the source dictionary.
"""

from __future__ import annotations

import argparse
import html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


LEFT_MARGIN = 90
RIGHT_MARGIN = 120
TOP_MARGIN = 130
BOTTOM_MARGIN = 100
COLUMN_GAP = 170
ROW_GAP = 58
MIN_NODE_WIDTH = 64
MAX_NODE_WIDTH = 148
NODE_HEIGHT = 34


def escape_attr(value: object) -> str:
    """Escape a value for HTML attributes."""

    return html.escape(str(value), quote=True)


def escape_text(value: object) -> str:
    """Escape a value for HTML text."""

    return html.escape(str(value), quote=False)


def node_width(label: str) -> int:
    """Return a stable node width for the visible label."""

    return max(MIN_NODE_WIDTH, min(MAX_NODE_WIDTH, 28 + len(label) * 9))


def first_seen_order(graph: dict[str, Any]) -> dict[str, int]:
    """Return first-seen order based on DAG edge order."""

    order: dict[str, int] = {}
    start_id = f"f:{graph.get('start_fragment', '')}"
    order[start_id] = 0
    next_index = 1

    for edge in graph["edges"]:
        for key in ("source", "target"):
            node_id = edge[key]
            if node_id not in order:
                order[node_id] = next_index
                next_index += 1

    for node in graph["nodes"]:
        node_id = node["id"]
        if node_id not in order:
            order[node_id] = next_index
            next_index += 1

    return order


def compute_layout(graph: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], int, int]:
    """Assign x/y positions to DAG nodes."""

    order = first_seen_order(graph)
    columns: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for node in graph["nodes"]:
        columns[int(node["depth"])].append(node)

    for depth, nodes in columns.items():
        nodes.sort(key=lambda node: (order[node["id"]], node["label"]))

    max_depth = max(columns) if columns else 0
    max_rows = max((len(nodes) for nodes in columns.values()), default=1)
    width = LEFT_MARGIN + RIGHT_MARGIN + max_depth * COLUMN_GAP + MAX_NODE_WIDTH
    height = TOP_MARGIN + BOTTOM_MARGIN + max_rows * ROW_GAP

    positioned: dict[str, dict[str, Any]] = {}
    for depth in sorted(columns):
        nodes = columns[depth]
        y_offset = (max_rows - len(nodes)) * ROW_GAP / 2
        for index, node in enumerate(nodes):
            label = node["label"]
            width_for_node = node_width(label)
            positioned[node["id"]] = {
                **node,
                "x": LEFT_MARGIN + depth * COLUMN_GAP,
                "y": TOP_MARGIN + y_offset + index * ROW_GAP,
                "width": width_for_node,
                "height": NODE_HEIGHT,
            }

    return positioned, width, height


def css_class_for_node(node: dict[str, Any]) -> str:
    """Return SVG/CSS classes for a node."""

    classes = ["node"]
    if node.get("terminal"):
        classes.append("terminal")
    if node.get("truncated"):
        classes.append("truncated")
    if node.get("turn"):
        classes.append(f"turn-{node['turn']}")
    status = str(node.get("status", "")).replace("_", "-")
    if status:
        classes.append(f"status-{status}")
    return " ".join(classes)


def css_class_for_edge(edge: dict[str, Any]) -> str:
    """Return SVG/CSS classes for an edge."""

    kind = str(edge["kind"]).replace("_", "-")
    mover = str(edge["mover"]).replace("_", "-")
    classes = ["edge", f"edge-{kind}", f"mover-{mover}"]
    if edge.get("is_strategy"):
        classes.append("strategy")
    return " ".join(classes)


def edge_path(source: dict[str, Any], target: dict[str, Any]) -> str:
    """Return an SVG cubic path between two nodes."""

    x1 = source["x"] + source["width"] / 2
    y1 = source["y"]
    x2 = target["x"] - target["width"] / 2
    y2 = target["y"]
    mid_x = (x1 + x2) / 2
    return f"M {x1:.1f} {y1:.1f} C {mid_x:.1f} {y1:.1f} {mid_x:.1f} {y2:.1f} {x2:.1f} {y2:.1f}"


def edge_label_position(source: dict[str, Any], target: dict[str, Any]) -> tuple[float, float]:
    """Return an approximate position for the edge letter."""

    x1 = source["x"] + source["width"] / 2
    y1 = source["y"]
    x2 = target["x"] - target["width"] / 2
    y2 = target["y"]
    return (x1 + x2) / 2, (y1 + y2) / 2 - 5


def render_svg(graph: dict[str, Any], nodes: dict[str, dict[str, Any]], width: int, height: int) -> str:
    """Render the graph body as SVG."""

    edges_markup: list[str] = []
    labels_markup: list[str] = []
    nodes_markup: list[str] = []

    for edge in graph["edges"]:
        source = nodes[edge["source"]]
        target = nodes[edge["target"]]
        label_x, label_y = edge_label_position(source, target)
        title = (
            f"{source['label']} + {edge['letter']} -> {target['label']}\n"
            f"{edge['kind']} by {edge['mover']}\n"
            f"{edge['move'].get('reason', '')}"
        )
        edges_markup.append(
            f'<path class="{css_class_for_edge(edge)}" '
            f'd="{edge_path(source, target)}" marker-end="url(#arrow)">'
            f"<title>{escape_text(title)}</title></path>"
        )
        labels_markup.append(
            f'<text class="edge-label" x="{label_x:.1f}" y="{label_y:.1f}">'
            f"{escape_text(edge['letter'])}</text>"
        )

    for node in nodes.values():
        x = node["x"] - node["width"] / 2
        y = node["y"] - node["height"] / 2
        title = (
            f"Fragment: {node['label']}\n"
            f"Status: {node['status']}\n"
            f"Turn: {node.get('turn') or 'terminal'}\n"
            f"Plies to end: {node.get('plies_to_end')}"
        )
        nodes_markup.append(
            f'<g class="{css_class_for_node(node)}" data-node-id="{escape_attr(node["id"])}">'
            f"<title>{escape_text(title)}</title>"
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{node["width"]}" '
            f'height="{node["height"]}" rx="6" ry="6"></rect>'
            f'<text x="{node["x"]:.1f}" y="{node["y"] + 4:.1f}">'
            f"{escape_text(node['label'])}</text>"
            "</g>"
        )

    return f"""
<svg id="graph" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-labelledby="graph-title graph-desc">
  <title id="graph-title">Ghost strategy DAG</title>
  <desc id="graph-desc">Solved Ghost strategy branches from the exported DAG.</desc>
  <defs>
    <marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">
      <path d="M0,0 L0,6 L9,3 z"></path>
    </marker>
  </defs>
  <g class="edges">
    {''.join(edges_markup)}
  </g>
  <g class="edge-labels">
    {''.join(labels_markup)}
  </g>
  <g class="nodes">
    {''.join(nodes_markup)}
  </g>
</svg>
"""


def render_html(graph: dict[str, Any], nodes: dict[str, dict[str, Any]], width: int, height: int) -> str:
    """Render a complete HTML page."""

    svg = render_svg(graph, nodes, width, height)
    safe_node_data = json.dumps(nodes, sort_keys=True).replace("</", "<\\/")
    root_moves = ", ".join(graph.get("root_moves", []))
    terminal_count = sum(1 for node in graph["nodes"] if node.get("terminal"))
    title = "Ghost Strategy DAG"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{
  --ink: #17201b;
  --muted: #5c6660;
  --line: #d5ddd8;
  --bot: #177245;
  --bot-soft: #e6f4ea;
  --opponent: #b42318;
  --opponent-soft: #fff1f0;
  --terminal: #6f7471;
  --terminal-soft: #f0f2f1;
  --strategy: #0f6b45;
  --option: #a43b32;
  --paper: #fbfcfb;
  --panel: #ffffff;
}}
* {{
  box-sizing: border-box;
}}
body {{
  margin: 0;
  color: var(--ink);
  background: var(--paper);
  font: 15px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}
header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 18px 22px;
  border-bottom: 1px solid var(--line);
  background: #ffffff;
}}
h1 {{
  margin: 0;
  font-size: 20px;
  font-weight: 700;
}}
.summary {{
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  color: var(--muted);
}}
.summary span {{
  white-space: nowrap;
}}
.layout {{
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  min-height: calc(100vh - 74px);
}}
.graph-wrap {{
  overflow: auto;
  padding: 22px;
}}
aside {{
  border-left: 1px solid var(--line);
  background: var(--panel);
  padding: 20px;
}}
.legend {{
  display: grid;
  gap: 8px;
  margin: 0 0 22px;
}}
.legend-row {{
  display: grid;
  grid-template-columns: 18px 1fr;
  align-items: center;
  gap: 9px;
  color: var(--muted);
}}
.sample {{
  width: 18px;
  height: 12px;
  border-radius: 6px;
  border: 2px solid currentColor;
}}
.sample.bot {{
  color: var(--bot);
  background: var(--bot-soft);
}}
.sample.opponent {{
  color: var(--opponent);
  background: var(--opponent-soft);
}}
.sample.terminal {{
  color: var(--terminal);
  background: var(--terminal-soft);
}}
#details {{
  color: var(--muted);
}}
#details h2 {{
  margin: 0 0 8px;
  color: var(--ink);
  font-size: 18px;
}}
#details dl {{
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 6px 10px;
  margin: 14px 0 0;
}}
#details dt {{
  color: var(--ink);
  font-weight: 700;
}}
#details dd {{
  margin: 0;
  word-break: break-word;
}}
svg {{
  display: block;
  min-width: 100%;
  background: #ffffff;
}}
.edge {{
  fill: none;
  stroke: var(--option);
  stroke-width: 1.5;
  opacity: 0.68;
}}
.edge.strategy {{
  stroke: var(--strategy);
  stroke-width: 3;
  opacity: 0.95;
}}
.edge-invalid-immediate-loss {{
  stroke-dasharray: 4 4;
}}
marker path {{
  fill: #49524d;
}}
.edge-label {{
  font-size: 12px;
  font-weight: 700;
  fill: var(--ink);
  paint-order: stroke;
  stroke: #ffffff;
  stroke-width: 4px;
  stroke-linejoin: round;
  text-anchor: middle;
}}
.node rect {{
  fill: #ffffff;
  stroke: var(--line);
  stroke-width: 1.5;
}}
.node.turn-bot rect {{
  fill: var(--bot-soft);
  stroke: var(--bot);
}}
.node.turn-opponent rect {{
  fill: var(--opponent-soft);
  stroke: var(--opponent);
}}
.node.terminal rect {{
  fill: var(--terminal-soft);
  stroke: var(--terminal);
}}
.node text {{
  fill: var(--ink);
  font-size: 13px;
  font-weight: 700;
  text-anchor: middle;
  pointer-events: none;
}}
.node {{
  cursor: pointer;
}}
.node.selected rect {{
  stroke: #111111;
  stroke-width: 3;
}}
@media (max-width: 900px) {{
  header {{
    align-items: flex-start;
    flex-direction: column;
  }}
  .layout {{
    grid-template-columns: 1fr;
  }}
  aside {{
    border-left: 0;
    border-top: 1px solid var(--line);
  }}
}}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="summary">
    <span>Root moves: {escape_text(root_moves)}</span>
    <span>{graph.get("node_count", len(graph["nodes"]))} nodes</span>
    <span>{graph.get("edge_count", len(graph["edges"]))} edges</span>
    <span>{terminal_count} terminal fragments</span>
  </div>
</header>
<div class="layout">
  <main class="graph-wrap">
    {svg}
  </main>
  <aside>
    <div class="legend" aria-label="Legend">
      <div class="legend-row"><span class="sample bot"></span><span>Bot turn / winning proof reply</span></div>
      <div class="legend-row"><span class="sample opponent"></span><span>Opponent turn / all replies covered</span></div>
      <div class="legend-row"><span class="sample terminal"></span><span>Terminal completed word</span></div>
    </div>
    <section id="details">
      <h2>Select a node</h2>
      <p>Click a fragment to inspect its proof status, valid replies, and terminal state.</p>
    </section>
  </aside>
</div>
<script>
const NODE_DATA = {safe_node_data};
const details = document.getElementById("details");
for (const node of document.querySelectorAll(".node")) {{
  node.addEventListener("click", () => {{
    document.querySelectorAll(".node.selected").forEach((item) => item.classList.remove("selected"));
    node.classList.add("selected");
    const data = NODE_DATA[node.dataset.nodeId];
    const valid = data.valid_letters && data.valid_letters.length ? data.valid_letters.join(", ") : "none";
    const invalid = data.invalid_letters && data.invalid_letters.length ? data.invalid_letters.join(", ") : "none";
    details.innerHTML = `
      <h2>${{data.label}}</h2>
      <dl>
        <dt>Status</dt><dd>${{data.status}}</dd>
        <dt>Turn</dt><dd>${{data.turn || "terminal"}}</dd>
        <dt>Depth</dt><dd>${{data.depth}}</dd>
        <dt>Plies</dt><dd>${{data.plies_to_end ?? "terminal"}}</dd>
        <dt>Valid</dt><dd>${{valid}}</dd>
        <dt>Invalid</dt><dd>${{invalid}}</dd>
      </dl>
    `;
  }});
}}
</script>
</body>
</html>
"""


def build_arg_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""

    parser = argparse.ArgumentParser(
        description="Render a Ghost strategy DAG JSON file as HTML."
    )
    parser.add_argument(
        "--dag",
        type=Path,
        default=Path("strategy.json"),
        help="strategy DAG JSON path (default: strategy.json)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("strategy.html"),
        help="output HTML path (default: strategy.html)",
    )
    return parser


def main() -> int:
    """CLI entry point."""

    parser = build_arg_parser()
    args = parser.parse_args()

    try:
        with args.dag.open("r", encoding="utf-8") as handle:
            graph = json.load(handle)
        nodes, width, height = compute_layout(graph)
        rendered = render_html(graph, nodes, width, height)
        args.output.write_text(rendered, encoding="utf-8")
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"error: {exc}")
        return 2

    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
