const state = {
  status: null,
  selected: null,
  selectedRow: null,
  selectedRoute: null,
  selectedMetadata: null,
  searchTimer: null,
  pollTimer: null,
  activeJobId: null,
  gamepadButtons: new Map(),
  gamepadRepeat: { key: null, at: 0 },
  browse: { mode: null, current: "", parent: null, previousFocus: null },
};

const elements = {
  ariaStatus: document.getElementById("ariaStatus"),
  zipStatus: document.getElementById("zipStatus"),
  subtitle: document.getElementById("subtitle"),
  query: document.getElementById("query"),
  searchCount: document.getElementById("searchCount"),
  results: document.getElementById("results"),
  clearButton: document.getElementById("clearButton"),
  selectedName: document.getElementById("selectedName"),
  selectedPath: document.getElementById("selectedPath"),
  metaCollection: document.getElementById("metaCollection"),
  metaSystem: document.getElementById("metaSystem"),
  metaRoute: document.getElementById("metaRoute"),
  metaSize: document.getElementById("metaSize"),
  metaCrc: document.getElementById("metaCrc"),
  metaSha: document.getElementById("metaSha"),
  destination: document.getElementById("destination"),
  defaultDirButton: document.getElementById("defaultDirButton"),
  browseRootButton: document.getElementById("browseRootButton"),
  routeOverride: document.getElementById("routeOverride"),
  autoRouteButton: document.getElementById("autoRouteButton"),
  browseSubfolderButton: document.getElementById("browseSubfolderButton"),
  extractToggle: document.getElementById("extractToggle"),
  rootFallbackToggle: document.getElementById("rootFallbackToggle"),
  legalConfirm: document.getElementById("legalConfirm"),
  downloadForm: document.getElementById("downloadForm"),
  downloadButton: document.getElementById("downloadButton"),
  jobStage: document.getElementById("jobStage"),
  jobPercent: document.getElementById("jobPercent"),
  progressBar: document.getElementById("progressBar"),
  queueList: document.getElementById("queueList"),
  outputs: document.getElementById("outputs"),
  jobLog: document.getElementById("jobLog"),
  browseDialog: document.getElementById("browseDialog"),
  browseTitle: document.getElementById("browseTitle"),
  browseCurrent: document.getElementById("browseCurrent"),
  browseList: document.getElementById("browseList"),
  browseCloseButton: document.getElementById("browseCloseButton"),
  browseParentButton: document.getElementById("browseParentButton"),
  browseSelectButton: document.getElementById("browseSelectButton"),
};

function setEmptyResults(message) {
  elements.results.innerHTML = `<div class="empty-note">${escapeHtml(message)}</div>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function normalizePath(path) {
  return String(path || "")
    .replaceAll("\\", "/")
    .replace(/^\.\//, "")
    .replace(/^\/+/, "");
}

function fileNameFromPath(path) {
  const normalized = normalizePath(path);
  return normalized.split("/").filter(Boolean).at(-1) || path || "";
}

function pathParts(path) {
  return normalizePath(path).split("/").filter(Boolean);
}

function setPill(element, label, found, optional = false) {
  element.textContent = label;
  element.classList.toggle("muted", !found);
  element.classList.toggle("warn", optional && !found);
}

function updateDownloadButton() {
  const ariaReady = Boolean(state.status?.dependencies?.aria2c?.found);
  const hasRoute = Boolean(elements.routeOverride.value.trim() || state.selectedRoute?.folder || elements.rootFallbackToggle.checked);
  elements.downloadButton.disabled = !state.selected || !elements.legalConfirm.checked || !ariaReady || !hasRoute;
  ensureControllerFocus();
}

async function loadStatus() {
  const response = await fetch("/api/status");
  state.status = await response.json();
  const deps = state.status.dependencies || {};
  setPill(elements.ariaStatus, deps.aria2c?.found ? "aria2c ready" : "aria2c missing", deps.aria2c?.found);
  setPill(elements.zipStatus, deps.sevenZip?.found ? "7z ready" : "7z optional", deps.sevenZip?.found, true);
  elements.destination.value =
    localStorage.getItem("minerva.destination") ||
    state.status.defaultDestination ||
    "";
  elements.subtitle.textContent = "Server metadata ready";
  updateDownloadButton();
}

async function search(query) {
  const trimmed = query.trim();
  if (trimmed.length < 3) {
    elements.searchCount.textContent = "Enter 3+ chars";
    setEmptyResults("Search terms appear here.");
    return;
  }
  elements.searchCount.textContent = "Searching";
  setEmptyResults("Loading archive index on first search.");
  try {
    const response = await fetch(`/api/search?q=${encodeURIComponent(trimmed)}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Search failed");
    renderResults(payload.results || [], payload.total || 0);
  } catch (error) {
    elements.searchCount.textContent = "Error";
    elements.results.innerHTML = `<div class="empty-note error">${escapeHtml(error.message)}</div>`;
  }
}

function renderResults(results, total) {
  elements.searchCount.textContent = total > results.length ? `${results.length} of ${total}` : `${total}`;
  if (!results.length) {
    setEmptyResults("No matching entries.");
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const result of results) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "result-button";
    button.dataset.path = result.path;
    if (state.selected?.path === result.path) button.classList.add("selected");
    button.innerHTML = `
      <span class="result-title">${escapeHtml(result.fileName)}</span>
      <span class="result-subtitle">${escapeHtml([result.collection, result.system].filter(Boolean).join(" / "))}</span>
    `;
    button.addEventListener("click", () => selectResult(result));
    fragment.appendChild(button);
  }
  elements.results.replaceChildren(fragment);
  ensureControllerFocus();
}

async function selectResult(result) {
  state.selected = result;
  state.selectedRow = null;
  state.selectedRoute = null;
  state.selectedMetadata = null;
  document.querySelectorAll(".result-button").forEach((button) => {
    button.classList.toggle("selected", button.dataset.path === result.path);
  });
  updateSelectionPanel(result);
  await loadRoute(result.path);
  elements.clearButton.disabled = false;
  updateDownloadButton();
  await loadMetadata(result.path);
}

async function loadMetadata(path) {
  elements.metaSize.textContent = "Looking up";
  try {
    const response = await fetch(`/api/metadata?path=${encodeURIComponent(path)}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Metadata lookup failed");
    state.selectedMetadata = payload;
    updateMetadata(payload);
  } catch (error) {
    elements.metaSize.textContent = "Unavailable";
    state.selectedMetadata = null;
  }
}

async function loadRoute(path) {
  elements.metaRoute.textContent = "Detecting";
  elements.routeOverride.value = "";
  try {
    const response = await fetch(`/api/route?path=${encodeURIComponent(path)}`);
    const payload = await response.json();
    if (!response.ok || !payload.route) throw new Error(payload.error || "No EmuDeck folder mapping found");
    state.selectedRoute = payload.route;
    elements.metaRoute.textContent = payload.route.folder;
    elements.routeOverride.placeholder = payload.route.folder;
  } catch (error) {
    state.selectedRoute = null;
    elements.metaRoute.textContent = "Unmapped";
    elements.routeOverride.placeholder = "Type EmuDeck folder, e.g. gba";
  }
}

function updateSelectionPanel(result) {
  const parts = pathParts(result.path);
  elements.selectedName.textContent = result.fileName || fileNameFromPath(result.path);
  elements.selectedPath.textContent = normalizePath(result.path);
  elements.metaCollection.textContent = parts[0] || "-";
  elements.metaSystem.textContent = parts[1] || "-";
  elements.metaRoute.textContent = "-";
  elements.metaSize.textContent = result.size || "-";
  elements.metaCrc.textContent = "-";
  elements.metaSha.textContent = "-";
}

function updateMetadata(row) {
  elements.metaSize.textContent = row.size || elements.metaSize.textContent || "-";
  elements.metaCrc.textContent = row.crc32 || "-";
  elements.metaSha.textContent = row.sha1 || "-";
}

function clearSelection() {
  state.selected = null;
  state.selectedRow = null;
  state.selectedRoute = null;
  state.selectedMetadata = null;
  elements.selectedName.textContent = "No ROM selected";
  elements.selectedPath.textContent = "Search and select one archive entry.";
  elements.metaCollection.textContent = "-";
  elements.metaSystem.textContent = "-";
  elements.metaRoute.textContent = "-";
  elements.metaSize.textContent = "-";
  elements.metaCrc.textContent = "-";
  elements.metaSha.textContent = "-";
  elements.routeOverride.value = "";
  elements.routeOverride.placeholder = "Auto-detected after selection";
  elements.clearButton.disabled = true;
  updateDownloadButton();
  document.querySelectorAll(".result-button").forEach((button) => button.classList.remove("selected"));
}

async function startDownload(event) {
  event.preventDefault();
  if (!state.selected) return;

  const destination = elements.destination.value.trim();
  if (!destination) {
    elements.jobStage.textContent = "Output directory required";
    return;
  }
  localStorage.setItem("minerva.destination", destination);

  elements.downloadButton.disabled = true;
  setJobUi({ stage: "Queueing", progress: 0, log: [] });
  const payload = {
    fullPath: state.selected.path,
    fileName: state.selected.fileName || fileNameFromPath(state.selected.path),
    torrent: state.selectedMetadata?.torrentUrl || state.selectedRow?.torrents || "",
    romsRoot: destination,
    systemFolderOverride: elements.routeOverride.value.trim(),
    allowRomsRootFallback: elements.rootFallbackToggle.checked,
    extract: elements.extractToggle.checked,
    legalConfirm: elements.legalConfirm.checked,
  };

  try {
    const response = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "Could not start download");
    state.activeJobId = body.id;
    pollQueue();
    updateDownloadButton();
  } catch (error) {
    setJobUi({ status: "error", stage: "Error", error: error.message, log: [error.message] });
    elements.downloadButton.disabled = false;
  }
}

async function pollQueue() {
  clearTimeout(state.pollTimer);
  try {
    const response = await fetch("/api/jobs");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Queue not available");
    const jobs = payload.jobs || [];
    setQueueUi(jobs);
    const active = jobs.find((job) => job.status === "running") || jobs.find((job) => job.id === state.activeJobId) || jobs.at(-1);
    if (active) setJobUi(active);
    if (!jobs.some((job) => job.status === "queued" || job.status === "running")) {
      updateDownloadButton();
      return;
    }
    updateDownloadButton();
  } catch (error) {
    setJobUi({ status: "error", stage: "Error", error: error.message, log: [error.message] });
    updateDownloadButton();
    return;
  }
  state.pollTimer = setTimeout(pollQueue, 1000);
}

function setQueueUi(jobs) {
  if (!jobs.length) {
    elements.queueList.innerHTML = "";
    return;
  }
  elements.queueList.innerHTML = jobs.slice(-8).reverse().map((job) => {
    const name = job.payload?.fileName || fileNameFromPath(job.payload?.fullPath || job.id);
    const progress = Number.isFinite(job.progress) ? ` ${job.progress}%` : "";
    return `<div class="queue-item ${escapeHtml(job.status)}">
      <span>${escapeHtml(name)}</span>
      <strong>${escapeHtml(job.status)}${escapeHtml(progress)}</strong>
    </div>`;
  }).join("");
}

function setJobUi(job) {
  const progress = Number.isFinite(job.progress) ? job.progress : 0;
  elements.jobStage.textContent = job.error ? `${job.stage}: ${job.error}` : job.stage || "Working";
  elements.jobStage.classList.toggle("error", job.status === "error");
  elements.jobPercent.textContent = Number.isFinite(job.progress) ? `${progress}%` : "-";
  elements.progressBar.style.width = `${Math.max(0, Math.min(100, progress))}%`;
  const outputs = job.outputs || [];
  elements.outputs.innerHTML = outputs.length
    ? outputs.map((item) => `<div>${escapeHtml(item)}</div>`).join("")
    : "";
  elements.jobLog.textContent = (job.log || []).join("\n");
  elements.jobLog.scrollTop = elements.jobLog.scrollHeight;
}

function bindEvents() {
  elements.query.addEventListener("input", () => {
    clearTimeout(state.searchTimer);
    state.searchTimer = setTimeout(() => search(elements.query.value), 220);
  });
  elements.clearButton.addEventListener("click", clearSelection);
  elements.legalConfirm.addEventListener("change", updateDownloadButton);
  elements.rootFallbackToggle.addEventListener("change", updateDownloadButton);
  elements.defaultDirButton.addEventListener("click", () => {
    elements.destination.value = state.status?.defaultDestination || "";
  });
  elements.browseRootButton.addEventListener("click", () => openBrowser("root"));
  elements.autoRouteButton.addEventListener("click", () => {
    elements.routeOverride.value = "";
    updateDownloadButton();
  });
  elements.browseSubfolderButton.addEventListener("click", () => openBrowser("subfolder"));
  elements.browseCloseButton.addEventListener("click", closeBrowser);
  elements.browseParentButton.addEventListener("click", () => {
    if (state.browse.parent !== null) browseTo(state.browse.parent);
  });
  elements.browseSelectButton.addEventListener("click", selectBrowsedPath);
  elements.routeOverride.addEventListener("input", updateDownloadButton);
  elements.downloadForm.addEventListener("submit", startDownload);
  document.querySelectorAll(".check-row").forEach((row) => {
    row.tabIndex = 0;
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        row.querySelector("input")?.click();
      }
    });
  });
  document.addEventListener("keydown", handleControllerKeyboard);
}

async function openBrowser(mode) {
  state.browse.mode = mode;
  state.browse.previousFocus = document.activeElement;
  elements.browseDialog.hidden = false;
  elements.browseTitle.textContent = mode === "root" ? "ROMs root" : "System subfolder";
  await browseTo(mode === "root" ? elements.destination.value : elements.routeOverride.value);
  elements.browseSelectButton.focus();
}

function closeBrowser() {
  elements.browseDialog.hidden = true;
  const previous = state.browse.previousFocus;
  state.browse = { mode: null, current: "", parent: null, previousFocus: null };
  if (previous?.focus) previous.focus({ preventScroll: true });
}

async function browseTo(path) {
  const mode = state.browse.mode;
  if (!mode) return;
  elements.browseList.innerHTML = `<div class="empty-note">Loading...</div>`;
  const params = new URLSearchParams({ mode, path: path || "" });
  if (mode === "subfolder") params.set("root", elements.destination.value.trim());
  try {
    const response = await fetch(`/api/browse?${params}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not browse folder");
    renderBrowse(payload);
  } catch (error) {
    elements.browseList.innerHTML = `<div class="empty-note error">${escapeHtml(error.message)}</div>`;
  }
}

function renderBrowse(payload) {
  state.browse.current = payload.current || "";
  state.browse.parent = payload.parent ?? null;
  elements.browseCurrent.textContent = payload.mode === "subfolder"
    ? `/${payload.current || ""}`
    : payload.current || "Computer";
  elements.browseParentButton.disabled = payload.parent === null;

  if (!payload.entries?.length) {
    elements.browseList.innerHTML = `<div class="empty-note">No child folders.</div>`;
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const entry of payload.entries) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "browse-entry";
    button.textContent = entry.name;
    button.addEventListener("click", () => browseTo(entry.path));
    fragment.appendChild(button);
  }
  elements.browseList.replaceChildren(fragment);
}

function selectBrowsedPath() {
  if (state.browse.mode === "root") {
    elements.destination.value = state.browse.current;
    localStorage.setItem("minerva.destination", elements.destination.value);
  } else if (state.browse.mode === "subfolder") {
    elements.routeOverride.value = state.browse.current;
    updateDownloadButton();
  }
  closeBrowser();
}

async function init() {
  bindEvents();
  setEmptyResults("Search terms appear here.");
  await loadStatus();
  pollQueue();
  requestAnimationFrame(() => {
    elements.query.focus();
    startGamepadNavigation();
  });
}

init();

function controllerTargets() {
  return Array.from(
    document.querySelectorAll(
      'button:not([disabled]), input:not([disabled]), .check-row[tabindex="0"], .result-button:not([disabled]), .browse-entry:not([disabled])',
    ),
  ).filter((element) => {
    const style = window.getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length > 0;
  });
}

function ensureControllerFocus() {
  const targets = controllerTargets();
  if (!targets.length) return;
  if (!targets.includes(document.activeElement)) {
    targets[0].focus();
  }
}

function handleControllerKeyboard(event) {
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  const arrows = {
    ArrowUp: "up",
    ArrowDown: "down",
    ArrowLeft: "left",
    ArrowRight: "right",
  };
  if (arrows[event.key]) {
    const isTextInput = event.target instanceof HTMLInputElement && event.target.type !== "checkbox";
    if (isTextInput && (event.key === "ArrowLeft" || event.key === "ArrowRight")) return;
    event.preventDefault();
    moveControllerFocus(arrows[event.key]);
    return;
  }
  if ((event.key === "Enter" || event.key === " ") && !isTypingTarget(event.target)) {
    const active = document.activeElement;
    if (active && active !== document.body) {
      event.preventDefault();
      activateControllerTarget(active);
    }
  }
}

function isTypingTarget(target) {
  return target instanceof HTMLInputElement && target.type !== "checkbox";
}

function moveControllerFocus(direction) {
  const targets = controllerTargets();
  if (!targets.length) return;
  const active = targets.includes(document.activeElement) ? document.activeElement : targets[0];
  const currentRect = active.getBoundingClientRect();
  const currentCenter = rectCenter(currentRect);
  let best = null;
  let bestScore = Number.POSITIVE_INFINITY;

  for (const target of targets) {
    if (target === active) continue;
    const rect = target.getBoundingClientRect();
    const center = rectCenter(rect);
    const dx = center.x - currentCenter.x;
    const dy = center.y - currentCenter.y;
    if (!isInDirection(direction, dx, dy)) continue;

    const primary = direction === "left" || direction === "right" ? Math.abs(dx) : Math.abs(dy);
    const secondary = direction === "left" || direction === "right" ? Math.abs(dy) : Math.abs(dx);
    const score = primary * 3 + secondary;
    if (score < bestScore) {
      best = target;
      bestScore = score;
    }
  }

  if (!best) {
    const index = targets.indexOf(active);
    const nextIndex = direction === "up" || direction === "left" ? Math.max(0, index - 1) : Math.min(targets.length - 1, index + 1);
    best = targets[nextIndex];
  }

  best.focus({ preventScroll: true });
  scrollIntoNearestPane(best);
}

function scrollIntoNearestPane(target) {
  const pane = target.closest(".results, .detail-pane");
  if (!pane) return;
  const paneRect = pane.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  if (targetRect.top < paneRect.top) {
    pane.scrollTop -= paneRect.top - targetRect.top + 8;
  } else if (targetRect.bottom > paneRect.bottom) {
    pane.scrollTop += targetRect.bottom - paneRect.bottom + 8;
  }
  if (targetRect.left < paneRect.left) {
    pane.scrollLeft -= paneRect.left - targetRect.left + 8;
  } else if (targetRect.right > paneRect.right) {
    pane.scrollLeft += targetRect.right - paneRect.right + 8;
  }
}

function rectCenter(rect) {
  return {
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2,
  };
}

function isInDirection(direction, dx, dy) {
  if (direction === "up") return dy < -4 && Math.abs(dy) >= Math.abs(dx) * 0.35;
  if (direction === "down") return dy > 4 && Math.abs(dy) >= Math.abs(dx) * 0.35;
  if (direction === "left") return dx < -4 && Math.abs(dx) >= Math.abs(dy) * 0.35;
  return dx > 4 && Math.abs(dx) >= Math.abs(dy) * 0.35;
}

function activateControllerTarget(target) {
  if (target.classList.contains("check-row")) {
    target.querySelector("input")?.click();
    return;
  }
  target.click();
}

function startGamepadNavigation() {
  const tick = () => {
    pollGamepads();
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

function pollGamepads() {
  const pads = navigator.getGamepads ? Array.from(navigator.getGamepads()).filter(Boolean) : [];
  if (!pads.length) return;
  const pad = pads[0];
  const direction =
    pressed(pad, 12) || axisPressed(pad, 1, -1) ? "up" :
    pressed(pad, 13) || axisPressed(pad, 1, 1) ? "down" :
    pressed(pad, 14) || axisPressed(pad, 0, -1) ? "left" :
    pressed(pad, 15) || axisPressed(pad, 0, 1) ? "right" :
    null;

  if (direction && shouldRepeat(direction)) {
    moveControllerFocus(direction);
  }
  if (!direction) {
    state.gamepadRepeat = { key: null, at: 0 };
  }

  if (buttonPressedOnce(pad, 0, "a")) {
    ensureControllerFocus();
    activateControllerTarget(document.activeElement);
  }
}

function pressed(pad, index) {
  return Boolean(pad.buttons[index]?.pressed);
}

function axisPressed(pad, index, sign) {
  const value = pad.axes[index] || 0;
  return sign < 0 ? value < -0.55 : value > 0.55;
}

function shouldRepeat(key) {
  const now = performance.now();
  const firstDelay = 260;
  const repeatDelay = 130;
  const delay = state.gamepadRepeat.key === key ? repeatDelay : firstDelay;
  if (state.gamepadRepeat.key !== key || now - state.gamepadRepeat.at >= delay) {
    state.gamepadRepeat = { key, at: now };
    return true;
  }
  return false;
}

function buttonPressedOnce(pad, index, key) {
  const isPressed = pressed(pad, index);
  const wasPressed = state.gamepadButtons.get(key) || false;
  state.gamepadButtons.set(key, isPressed);
  return isPressed && !wasPressed;
}
