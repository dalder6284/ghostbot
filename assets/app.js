"use strict";

const ASSET_VERSION = "20260418-graph-3";

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
  zoom: {
    scale: 1,
    min: 0.2,
    max: 2.5,
    baseWidth: 0,
    baseHeight: 0,
    canvas: null,
    svg: null,
  },
  pointers: new Map(),
  gesture: null,
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
  if (!scroll) {
    throw new Error("Graph container is missing from index.html");
  }
  const graphPanel = document.getElementById("graph-panel");
  if (!graphPanel) {
    throw new Error("Graph panel is missing from index.html");
  }
  const tabId = GRAPH_CONFIG[key].tabId;
  graphPanel.setAttribute("aria-labelledby", tabId);

  scroll.replaceChildren();
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
  const canvas = createElement("div", { class: "graph-canvas" });
  canvas.appendChild(svg);
  scroll.appendChild(canvas);
  setupZoom(layout, canvas, svg);
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

function updateTabs(activeKey) {
  for (const [key, config] of Object.entries(GRAPH_CONFIG)) {
    const tab = document.getElementById(config.tabId);
    const isActive = key === activeKey;
    tab.classList.toggle("is-active", isActive);
    tab.setAttribute("aria-selected", String(isActive));
  }
}

function setupZoom(layout, canvas, svg) {
  state.zoom.baseWidth = layout.width;
  state.zoom.baseHeight = layout.height;
  state.zoom.canvas = canvas;
  state.zoom.svg = svg;
  state.zoom.max = 2.5;
  state.zoom.min = fitScaleForCurrentView(layout);
  state.zoom.scale = Math.max(state.zoom.min, Math.min(1, state.zoom.max));
  applyZoom();

  const scroll = document.getElementById("graph-scroll");
  scroll.scrollLeft = 0;
  scroll.scrollTop = 0;
}

function fitScaleForCurrentView(layout) {
  const scroll = document.getElementById("graph-scroll");
  const visibleWidth = Math.max(1, scroll.clientWidth - 28);
  const visibleHeight = Math.max(1, scroll.clientHeight - 28);
  return Math.min(1, visibleWidth / layout.width, visibleHeight / layout.height);
}

function applyZoom() {
  const zoom = state.zoom;
  if (!zoom.canvas || !zoom.svg) {
    return;
  }

  const scaledWidth = Math.max(1, zoom.baseWidth * zoom.scale);
  const scaledHeight = Math.max(1, zoom.baseHeight * zoom.scale);
  zoom.canvas.style.width = `${scaledWidth}px`;
  zoom.canvas.style.height = `${scaledHeight}px`;
  zoom.svg.setAttribute("width", String(zoom.baseWidth));
  zoom.svg.setAttribute("height", String(zoom.baseHeight));
  zoom.svg.style.transform = `scale(${zoom.scale})`;
}

function clampZoom(scale) {
  return Math.max(state.zoom.min, Math.min(state.zoom.max, scale));
}

function setZoom(nextScale, viewportX = null, viewportY = null) {
  const scroll = document.getElementById("graph-scroll");
  const oldScale = state.zoom.scale;
  const newScale = clampZoom(nextScale);
  if (Math.abs(newScale - oldScale) < 0.001) {
    return;
  }

  const focusX = viewportX ?? scroll.clientWidth / 2;
  const focusY = viewportY ?? scroll.clientHeight / 2;
  const oldWidth = Math.max(1, state.zoom.baseWidth * oldScale);
  const oldHeight = Math.max(1, state.zoom.baseHeight * oldScale);
  const ratioX = (scroll.scrollLeft + focusX) / oldWidth;
  const ratioY = (scroll.scrollTop + focusY) / oldHeight;

  state.zoom.scale = newScale;
  applyZoom();

  const newWidth = Math.max(1, state.zoom.baseWidth * newScale);
  const newHeight = Math.max(1, state.zoom.baseHeight * newScale);
  scroll.scrollLeft = ratioX * newWidth - focusX;
  scroll.scrollTop = ratioY * newHeight - focusY;
}

function zoomBy(factor, clientX = null, clientY = null) {
  const scroll = document.getElementById("graph-scroll");
  let viewportX = null;
  let viewportY = null;
  if (clientX !== null && clientY !== null) {
    const rect = scroll.getBoundingClientRect();
    viewportX = clientX - rect.left;
    viewportY = clientY - rect.top;
  }
  setZoom(state.zoom.scale * factor, viewportX, viewportY);
}

function bindGraphInteractions() {
  const scroll = document.getElementById("graph-scroll");
  if (!scroll) {
    return;
  }
  scroll.addEventListener(
    "wheel",
    (event) => {
      if (!event.ctrlKey && !event.metaKey) {
        return;
      }
      event.preventDefault();
      const factor = Math.exp(-event.deltaY * 0.0015);
      zoomBy(factor, event.clientX, event.clientY);
    },
    { passive: false },
  );

  scroll.addEventListener("pointerdown", handlePointerDown);
  scroll.addEventListener("pointermove", handlePointerMove);
  scroll.addEventListener("pointerup", handlePointerEnd);
  scroll.addEventListener("pointercancel", handlePointerEnd);
}

function handlePointerDown(event) {
  const scroll = document.getElementById("graph-scroll");
  scroll.setPointerCapture(event.pointerId);
  state.pointers.set(event.pointerId, {
    x: event.clientX,
    y: event.clientY,
  });
  resetGesture();
}

function handlePointerMove(event) {
  if (!state.pointers.has(event.pointerId)) {
    return;
  }

  state.pointers.set(event.pointerId, {
    x: event.clientX,
    y: event.clientY,
  });

  const scroll = document.getElementById("graph-scroll");
  if (state.pointers.size === 1) {
    event.preventDefault();
    const pointer = state.pointers.values().next().value;
    if (!state.gesture || state.gesture.type !== "pan") {
      state.gesture = {
        type: "pan",
        x: pointer.x,
        y: pointer.y,
        scrollLeft: scroll.scrollLeft,
        scrollTop: scroll.scrollTop,
      };
    }
    scroll.scrollLeft = state.gesture.scrollLeft - (pointer.x - state.gesture.x);
    scroll.scrollTop = state.gesture.scrollTop - (pointer.y - state.gesture.y);
    return;
  }

  if (state.pointers.size === 2) {
    event.preventDefault();
    const [a, b] = Array.from(state.pointers.values());
    const distance = pointerDistance(a, b);
    const center = pointerCenter(a, b);
    const rect = scroll.getBoundingClientRect();
    const viewportX = center.x - rect.left;
    const viewportY = center.y - rect.top;
    if (!state.gesture || state.gesture.type !== "pinch") {
      state.gesture = {
        type: "pinch",
        distance,
        scale: state.zoom.scale,
        graphX: (scroll.scrollLeft + viewportX) / state.zoom.scale,
        graphY: (scroll.scrollTop + viewportY) / state.zoom.scale,
      };
      return;
    }
    const nextScale = clampZoom(
      state.gesture.scale * (distance / state.gesture.distance),
    );
    state.zoom.scale = nextScale;
    applyZoom();
    scroll.scrollLeft = state.gesture.graphX * nextScale - viewportX;
    scroll.scrollTop = state.gesture.graphY * nextScale - viewportY;
  }
}

function handlePointerEnd(event) {
  state.pointers.delete(event.pointerId);
  resetGesture();
}

function resetGesture() {
  state.gesture = null;
}

function pointerDistance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function pointerCenter(a, b) {
  return {
    x: (a.x + b.x) / 2,
    y: (a.y + b.y) / 2,
  };
}

function handleResize() {
  if (!state.zoom.canvas || !state.zoom.svg) {
    return;
  }
  state.zoom.min = fitScaleForCurrentView({
    width: state.zoom.baseWidth,
    height: state.zoom.baseHeight,
  });
  if (state.zoom.scale < state.zoom.min) {
    state.zoom.scale = state.zoom.min;
    applyZoom();
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
      const response = await fetch(`${config.path}?v=${ASSET_VERSION}`);
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
  bindGraphInteractions();
  window.addEventListener("resize", handleResize);
  if (window.location.hash === "#second-player") {
    state.activeKey = "second";
  }

  try {
    await loadGraphs();
    renderGraph(state.activeKey);
  } catch (error) {
    const meta = document.getElementById("graph-meta");
    const scroll = document.getElementById("graph-scroll");
    if (meta) {
      meta.textContent = "Unable to load graph data.";
    }
    const message = createElement("p", { class: "status-message" });
    message.textContent = `${error.message}. Serve this folder through GitHub Pages or another local web server.`;
    if (scroll) {
      scroll.replaceChildren(message);
    } else {
      document.body.appendChild(message);
    }
  }
}

document.addEventListener("DOMContentLoaded", init);
