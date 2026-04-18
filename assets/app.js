"use strict";

const GRAPH_CONFIG = {
  first: {
    path: "data/first_player_strategy.json",
    tabId: "tab-first",
    title: "First Player",
  },
  second: {
    path: "data/second_player_strategy.json",
    tabId: "tab-second",
    title: "Second Player",
  },
};

const SVG_NS = "http://www.w3.org/2000/svg";
const LAYOUT = {
  leftMargin: 90,
  rightMargin: 120,
  topMargin: 130,
  bottomMargin: 100,
  columnGap: 170,
  rowGap: 58,
  minNodeWidth: 64,
  maxNodeWidth: 148,
  nodeHeight: 34,
};

const state = {
  activeKey: "first",
  graphs: {},
};

function createElement(name, attrs = {}) {
  const element = document.createElement(name);
  for (const [key, value] of Object.entries(attrs)) {
    element.setAttribute(key, value);
  }
  return element;
}

function createSvgElement(name, attrs = {}) {
  const element = document.createElementNS(SVG_NS, name);
  for (const [key, value] of Object.entries(attrs)) {
    element.setAttribute(key, value);
  }
  return element;
}

function cssToken(value) {
  return String(value).replaceAll("_", "-");
}

function displayLabel(label) {
  if (label.length <= 14) {
    return label;
  }
  return `${label.slice(0, 11)}...`;
}

function nodeWidth(label) {
  return Math.max(
    LAYOUT.minNodeWidth,
    Math.min(LAYOUT.maxNodeWidth, 28 + displayLabel(label).length * 9),
  );
}

function firstSeenOrder(graph) {
  const order = new Map();
  const startId = `f:${graph.start_fragment || ""}`;
  let nextIndex = 0;
  order.set(startId, nextIndex);
  nextIndex += 1;

  for (const edge of graph.edges) {
    for (const key of ["source", "target"]) {
      if (!order.has(edge[key])) {
        order.set(edge[key], nextIndex);
        nextIndex += 1;
      }
    }
  }

  for (const node of graph.nodes) {
    if (!order.has(node.id)) {
      order.set(node.id, nextIndex);
      nextIndex += 1;
    }
  }

  return order;
}

function computeLayout(graph) {
  const order = firstSeenOrder(graph);
  const columns = new Map();
  for (const node of graph.nodes) {
    const depth = Number(node.depth);
    if (!columns.has(depth)) {
      columns.set(depth, []);
    }
    columns.get(depth).push(node);
  }

  for (const nodes of columns.values()) {
    nodes.sort((a, b) => {
      const orderDelta = order.get(a.id) - order.get(b.id);
      if (orderDelta !== 0) {
        return orderDelta;
      }
      return a.label.localeCompare(b.label);
    });
  }

  const depths = Array.from(columns.keys());
  const maxDepth = Math.max(...depths, 0);
  const maxRows = Math.max(...Array.from(columns.values(), (nodes) => nodes.length), 1);
  const width =
    LAYOUT.leftMargin +
    LAYOUT.rightMargin +
    maxDepth * LAYOUT.columnGap +
    LAYOUT.maxNodeWidth;
  const height = LAYOUT.topMargin + LAYOUT.bottomMargin + maxRows * LAYOUT.rowGap;
  const positioned = new Map();

  for (const depth of depths.sort((a, b) => a - b)) {
    const nodes = columns.get(depth);
    const yOffset = ((maxRows - nodes.length) * LAYOUT.rowGap) / 2;
    nodes.forEach((node, index) => {
      const widthForNode = nodeWidth(node.label);
      positioned.set(node.id, {
        ...node,
        x: LAYOUT.leftMargin + depth * LAYOUT.columnGap,
        y: LAYOUT.topMargin + yOffset + index * LAYOUT.rowGap,
        width: widthForNode,
        height: LAYOUT.nodeHeight,
      });
    });
  }

  return { nodes: positioned, width, height };
}

function nodeClasses(node) {
  const classes = ["node"];
  if (node.terminal) {
    classes.push("terminal");
  }
  if (node.truncated) {
    classes.push("truncated");
  }
  if (node.turn) {
    classes.push(`turn-${cssToken(node.turn)}`);
  }
  if (node.status) {
    classes.push(`status-${cssToken(node.status)}`);
  }
  return classes.join(" ");
}

function edgeClasses(edge) {
  const classes = [
    "edge",
    `edge-${cssToken(edge.kind)}`,
    `mover-${cssToken(edge.mover)}`,
  ];
  if (edge.is_strategy) {
    classes.push("strategy");
  }
  return classes.join(" ");
}

function edgePath(source, target) {
  const x1 = source.x + source.width / 2;
  const y1 = source.y;
  const x2 = target.x - target.width / 2;
  const y2 = target.y;
  const midX = (x1 + x2) / 2;
  return `M ${x1.toFixed(1)} ${y1.toFixed(1)} C ${midX.toFixed(1)} ${y1.toFixed(1)} ${midX.toFixed(1)} ${y2.toFixed(1)} ${x2.toFixed(1)} ${y2.toFixed(1)}`;
}

function edgeLabelPosition(source, target) {
  const x1 = source.x + source.width / 2;
  const y1 = source.y;
  const x2 = target.x - target.width / 2;
  const y2 = target.y;
  return {
    x: (x1 + x2) / 2,
    y: (y1 + y2) / 2 - 5,
  };
}

function appendSvgTitle(parent, text) {
  const title = createSvgElement("title");
  title.textContent = text;
  parent.appendChild(title);
}

function renderGraph(key) {
  const graph = state.graphs[key];
  const scroll = document.getElementById("graph-scroll");
  const tabId = GRAPH_CONFIG[key].tabId;
  document.getElementById("graph-panel").setAttribute("aria-labelledby", tabId);

  scroll.replaceChildren();
  resetDetails();
  updateTabs(key);

  if (!graph) {
    const message = createElement("p", { class: "status-message" });
    message.textContent = "Graph data is not available.";
    scroll.appendChild(message);
    return;
  }

  const layout = computeLayout(graph);
  updateMeta(graph);
  const svg = buildSvg(graph, layout);
  scroll.appendChild(svg);
}

function buildSvg(graph, layout) {
  const svg = createSvgElement("svg", {
    id: "graph",
    class: "graph-svg",
    viewBox: `0 0 ${layout.width} ${layout.height}`,
    width: String(layout.width),
    height: String(layout.height),
    role: "img",
    "aria-label": "Ghost strategy DAG",
  });

  const defs = createSvgElement("defs");
  const marker = createSvgElement("marker", {
    id: "arrow",
    markerWidth: "10",
    markerHeight: "10",
    refX: "8",
    refY: "3",
    orient: "auto",
    markerUnits: "strokeWidth",
  });
  marker.appendChild(createSvgElement("path", { d: "M0,0 L0,6 L9,3 z" }));
  defs.appendChild(marker);
  svg.appendChild(defs);

  const edgesGroup = createSvgElement("g", { class: "edges" });
  const labelsGroup = createSvgElement("g", { class: "edge-labels" });
  const nodesGroup = createSvgElement("g", { class: "nodes" });

  for (const edge of graph.edges) {
    const source = layout.nodes.get(edge.source);
    const target = layout.nodes.get(edge.target);
    if (!source || !target) {
      continue;
    }

    const path = createSvgElement("path", {
      class: edgeClasses(edge),
      d: edgePath(source, target),
      "marker-end": "url(#arrow)",
    });
    appendSvgTitle(
      path,
      `${source.label} + ${edge.letter} -> ${target.label}\n${edge.kind} by ${edge.mover}\n${edge.move.reason || ""}`,
    );
    edgesGroup.appendChild(path);

    const labelPosition = edgeLabelPosition(source, target);
    const label = createSvgElement("text", {
      class: "edge-label",
      x: labelPosition.x.toFixed(1),
      y: labelPosition.y.toFixed(1),
    });
    label.textContent = edge.letter;
    labelsGroup.appendChild(label);
  }

  for (const node of layout.nodes.values()) {
    nodesGroup.appendChild(buildNode(node));
  }

  svg.appendChild(edgesGroup);
  svg.appendChild(labelsGroup);
  svg.appendChild(nodesGroup);
  return svg;
}

function buildNode(node) {
  const group = createSvgElement("g", {
    class: nodeClasses(node),
    "data-node-id": node.id,
    role: "button",
    tabindex: "0",
  });
  appendSvgTitle(
    group,
    `Fragment: ${node.label}\nStatus: ${node.status}\nTurn: ${node.turn || "terminal"}\nPlies to end: ${node.plies_to_end}`,
  );

  const rect = createSvgElement("rect", {
    x: (node.x - node.width / 2).toFixed(1),
    y: (node.y - node.height / 2).toFixed(1),
    width: String(node.width),
    height: String(node.height),
    rx: "6",
    ry: "6",
  });
  group.appendChild(rect);

  const text = createSvgElement("text", {
    x: node.x.toFixed(1),
    y: (node.y + 4).toFixed(1),
  });
  text.textContent = displayLabel(node.label);
  group.appendChild(text);

  group.addEventListener("click", () => selectNode(group, node));
  group.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectNode(group, node);
    }
  });

  return group;
}

function selectNode(element, node) {
  document
    .querySelectorAll(".node.selected")
    .forEach((selected) => selected.classList.remove("selected"));
  element.classList.add("selected");
  updateDetails(node);
}

function updateMeta(graph) {
  const meta = document.getElementById("graph-meta");
  const terminalCount = graph.nodes.filter((node) => node.terminal).length;
  const rootMoves = graph.root_moves.join(", ");
  const mode =
    graph.mode === "second_player_response"
      ? "Second player response"
      : "First player openings";

  meta.replaceChildren(
    metaItem(mode),
    metaItem(`Root moves: ${rootMoves}`),
    metaItem(`${graph.node_count} nodes`),
    metaItem(`${graph.edge_count} edges`),
    metaItem(`${terminalCount} terminal fragments`),
  );
}

function metaItem(text) {
  const item = createElement("span");
  item.textContent = text;
  return item;
}

function resetDetails() {
  const details = document.getElementById("details");
  details.replaceChildren();
  const heading = createElement("h2");
  heading.textContent = "Select a Fragment";
  const text = createElement("p");
  text.textContent =
    "Click a node to inspect its turn, proof status, valid continuations, and invalid letters.";
  details.append(heading, text);
}

function updateDetails(node) {
  const details = document.getElementById("details");
  const heading = createElement("h2");
  heading.textContent = node.label;
  const list = createElement("dl");
  const values = [
    ["Status", node.status],
    ["Turn", node.turn || "terminal"],
    ["Depth", node.depth],
    ["Plies", node.plies_to_end ?? "terminal"],
    ["Valid", formatLetters(node.valid_letters)],
    ["Invalid", formatLetters(node.invalid_letters)],
  ];

  details.replaceChildren(heading, list);
  for (const [label, value] of values) {
    const term = createElement("dt");
    const description = createElement("dd");
    term.textContent = label;
    description.textContent = String(value);
    list.append(term, description);
  }
}

function formatLetters(letters) {
  if (!letters || letters.length === 0) {
    return "none";
  }
  return letters.join(", ");
}

function updateTabs(activeKey) {
  for (const [key, config] of Object.entries(GRAPH_CONFIG)) {
    const tab = document.getElementById(config.tabId);
    const isActive = key === activeKey;
    tab.classList.toggle("is-active", isActive);
    tab.setAttribute("aria-selected", String(isActive));
  }
}

function setActiveGraph(key) {
  if (!GRAPH_CONFIG[key]) {
    return;
  }
  state.activeKey = key;
  renderGraph(key);
  const hash = key === "second" ? "#second-player" : "#first-player";
  if (window.location.hash !== hash) {
    window.history.replaceState(null, "", hash);
  }
}

async function loadGraphs() {
  const entries = await Promise.all(
    Object.entries(GRAPH_CONFIG).map(async ([key, config]) => {
      const response = await fetch(config.path);
      if (!response.ok) {
        throw new Error(`Could not load ${config.path}`);
      }
      return [key, await response.json()];
    }),
  );
  state.graphs = Object.fromEntries(entries);
}

function bindTabs() {
  for (const [key, config] of Object.entries(GRAPH_CONFIG)) {
    document.getElementById(config.tabId).addEventListener("click", () => {
      setActiveGraph(key);
    });
  }
}

async function init() {
  bindTabs();
  if (window.location.hash === "#second-player") {
    state.activeKey = "second";
  }

  try {
    await loadGraphs();
    renderGraph(state.activeKey);
  } catch (error) {
    const meta = document.getElementById("graph-meta");
    const scroll = document.getElementById("graph-scroll");
    meta.textContent = "Unable to load graph data.";
    const message = createElement("p", { class: "status-message" });
    message.textContent = `${error.message}. Serve this folder through GitHub Pages or another local web server.`;
    scroll.replaceChildren(message);
  }
}

document.addEventListener("DOMContentLoaded", init);
