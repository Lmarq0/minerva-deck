import { ControllerInput, createGamepadPoller } from "./controller.js";

const state = {
  status: null,
  games: [],
  systemFilter: "all",
  selectedGame: null,
  selectedVariant: null,
  routeOverride: "",
  searchTimer: null,
  searchPollTimer: null,
  searchRequest: 0,
  searchAbort: null,
  pollTimer: null,
  jobs: [],
  activeJobId: null,
  selectedJobId: null,
  downloadsFilter: "all",
  overlayReturnFocus: null,
};

const sessionToken =
  document.querySelector('meta[name="minerva-session-token"]')?.content || "";

function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-Minerva-Session", sessionToken);
  return fetch(url, { ...options, headers });
}

const byId = (id) => document.getElementById(id);
const elements = {
  query: byId("query"),
  clearQueryButton: byId("clearQueryButton"),
  settingsButton: byId("settingsButton"),
  downloadsButton: byId("downloadsButton"),
  queueBadge: byId("queueBadge"),
  setupBanner: byId("setupBanner"),
  setupBannerText: byId("setupBannerText"),
  dismissSetupButton: byId("dismissSetupButton"),
  systemChips: byId("systemChips"),
  searchCount: byId("searchCount"),
  results: byId("results"),
  detailEmpty: byId("detailEmpty"),
  detailCard: byId("detailCard"),
  detailCover: byId("detailCover"),
  detailTitle: byId("detailTitle"),
  detailSystem: byId("detailSystem"),
  detailSource: byId("detailSource"),
  variantList: byId("variantList"),
  destinationSummary: byId("destinationSummary"),
  destinationHint: byId("destinationHint"),
  browseSubfolderButton: byId("browseSubfolderButton"),
  legalRow: byId("legalRow"),
  legalConfirm: byId("legalConfirm"),
  downloadButton: byId("downloadButton"),
  downloadHelp: byId("downloadHelp"),
  tray: byId("tray"),
  trayName: byId("trayName"),
  trayStatus: byId("trayStatus"),
  trayProgress: byId("trayProgress"),
  trayCancelButton: byId("trayCancelButton"),
  trayOpenButton: byId("trayOpenButton"),
  hintAccept: byId("hintAccept"),
  settingsDialog: byId("settingsDialog"),
  settingsCloseButton: byId("settingsCloseButton"),
  destination: byId("destination"),
  browseRootButton: byId("browseRootButton"),
  defaultDirButton: byId("defaultDirButton"),
  extractToggle: byId("extractToggle"),
  rootFallbackToggle: byId("rootFallbackToggle"),
  allFilesToggle: byId("allFilesToggle"),
  catalogInfo: byId("catalogInfo"),
  downloadsDialog: byId("downloadsDialog"),
  downloadsCloseButton: byId("downloadsCloseButton"),
  downloadFilters: document.querySelectorAll("[data-download-filter]"),
  downloadsActiveCount: byId("downloadsActiveCount"),
  downloadsCompletedCount: byId("downloadsCompletedCount"),
  downloadsIssueCount: byId("downloadsIssueCount"),
  downloadsList: byId("downloadsList"),
  downloadsDetail: byId("downloadsDetail"),
};

/* Formatting */

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

// Polling re-renders the same markup every second during a download; skipping
// identical writes avoids needless layout and paint work in WebEngine.
const renderedHtml = new WeakMap();
function setHtml(element, html) {
  if (renderedHtml.get(element) === html) return;
  renderedHtml.set(element, html);
  element.innerHTML = html;
}

function formatBytes(value) {
  let size = Number(value || 0);
  const units = ["B", "KB", "MB", "GB", "TB"];
  let unit = units[0];
  for (const candidate of units) {
    unit = candidate;
    if (size < 1024 || candidate === units.at(-1)) break;
    size /= 1024;
  }
  return unit === "B" ? `${size} B` : `${size >= 100 ? size.toFixed(0) : size.toFixed(1)} ${unit}`;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0) return "";
  if (seconds < 60) return `${Math.ceil(seconds)}s left`;
  if (seconds < 3600) return `${Math.ceil(seconds / 60)}m left`;
  return `${Math.floor(seconds / 3600)}h ${Math.ceil((seconds % 3600) / 60)}m left`;
}

function formatTimestamp(value) {
  if (!value) return "";
  const date = new Date(Number(value));
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function fileNameFromPath(path) {
  return String(path || "").split("/").filter(Boolean).at(-1) || "";
}

const SYSTEM_NAMES = {
  "3do": "3DO", amiga: "Amiga", arcade: "Arcade", atari2600: "Atari 2600", atari7800: "Atari 7800",
  atarilynx: "Lynx", atarijaguar: "Jaguar", c64: "C64", dos: "DOS", dreamcast: "Dreamcast",
  famicom: "Famicom", fds: "FDS", gameandwatch: "Game & Watch", gamegear: "Game Gear", gb: "Game Boy",
  gba: "GBA", gbc: "GBC", gc: "GameCube", genesis: "Genesis", mastersystem: "Master System",
  megacd: "Mega CD", megadrive: "Mega Drive", msx: "MSX", n3ds: "3DS", n64: "N64", nds: "DS",
  neogeo: "Neo Geo", nes: "NES", ngp: "NGP", ngpc: "NGPC", pcengine: "PC Engine", ps2: "PS2",
  ps3: "PS3", psp: "PSP", "psvita/ux0": "Vita", psx: "PS1", saturn: "Saturn", sega32x: "32X",
  segacd: "Sega CD", sfc: "Super Famicom", snes: "SNES", switch: "Switch", virtualboy: "Virtual Boy",
  wii: "Wii", "wiiu/roms": "Wii U", wonderswan: "WonderSwan", wonderswancolor: "WonderSwan Color",
  xbox: "Xbox", "xbox360/roms": "Xbox 360",
};

function systemName(game) {
  return SYSTEM_NAMES[game.route?.folder] || game.platform || "Unknown system";
}

const REGION_SHORT = { USA: "USA", Europe: "EUR", Japan: "JPN", World: "World", Brazil: "BRA", Korea: "KOR", Australia: "AUS" };

function gameRegions(game) {
  return [...new Set(game.variants.map((variant) => REGION_SHORT[variant.region]).filter(Boolean))];
}

function variantStem(variant) {
  return variant.fileName.replace(/\.(tar\.(gz|bz2|xz)|[a-z0-9]{1,6})$/i, "");
}

function jobName(job) {
  return job?.payload?.title || job?.payload?.fileName || fileNameFromPath(job?.payload?.fullPath) || "Download";
}

function jobStatusLabel(status) {
  return { queued: "Queued", running: "Downloading", done: "Completed", error: "Failed", cancelled: "Cancelled" }[status] || "Unknown";
}

function jobMatchesFilter(job, filter) {
  if (filter === "active") return ["queued", "running"].includes(job.status);
  if (filter === "done") return job.status === "done";
  if (filter === "issues") return ["error", "cancelled"].includes(job.status);
  return true;
}

/* Covers: fetched through the authenticated API, cached as object URLs */

const coverUrls = new Map();
const coverQueue = [];
let coversLoading = 0;

function coverKey(game) {
  return game.coverSystem ? `${game.coverSystem}\n${variantStem(game.variants[0])}` : null;
}

function coverPlaceholder(game) {
  return escapeHtml(SYSTEM_NAMES[game.route?.folder] || "");
}

function paintCover(element, game) {
  const key = coverKey(game);
  const url = key ? coverUrls.get(key) : null;
  element.innerHTML = url ? `<img alt="" src="${url}" />` : coverPlaceholder(game);
  if (key && !coverUrls.has(key) && !coverQueue.some((item) => item.key === key)) {
    coverQueue.push({ key, game });
    pumpCovers();
  }
}

function pumpCovers() {
  while (coversLoading < 4 && coverQueue.length) {
    const { key, game } = coverQueue.shift();
    coversLoading += 1;
    const params = new URLSearchParams({ system: game.coverSystem, title: variantStem(game.variants[0]) });
    apiFetch(`/api/cover?${params}`)
      .then((response) => (response.ok ? response.blob() : null))
      .catch(() => null)
      .then((blob) => {
        coverUrls.set(key, blob ? URL.createObjectURL(blob) : null);
        if (!blob) return;
        for (const element of document.querySelectorAll("[data-cover-key]")) {
          if (element.dataset.coverKey === key) element.innerHTML = `<img alt="" src="${coverUrls.get(key)}" />`;
        }
      })
      .finally(() => {
        coversLoading -= 1;
        pumpCovers();
      });
  }
}

/* Status and settings */

function setBanner(message) {
  elements.setupBanner.hidden = !message;
  elements.setupBannerText.textContent = message || "";
}

async function loadStatus() {
  try {
    const response = await apiFetch("/api/status");
    if (!response.ok) throw new Error("The local service is unavailable.");
    state.status = await response.json();
    const capabilities = state.status.capabilities || {};
    if (!capabilities.torrentDownload?.ready) {
      setBanner("The download engine could not start. Use an official build of MiNERVA Deck.");
    } else if (!capabilities.archiveExtraction?.ready) {
      setBanner("Archive extraction is unavailable; downloads will be kept as archives.");
    }
    // The system folder dialog needs the desktop window; paths can still be typed.
    const canPickFolders = Boolean(state.status.runtime?.desktop);
    elements.browseRootButton.hidden = !canPickFolders;
    elements.browseSubfolderButton.hidden = !canPickFolders;
    elements.destination.value =
      localStorage.getItem("minerva.destination") || state.status.defaultDestination || "";
    const index = state.status.searchIndex || {};
    elements.catalogInfo.textContent = index.ready
      ? `Search catalog: ${Number(index.count || 0).toLocaleString()} files, updated ${formatTimestamp(index.loadedAt)}.`
      : "";
  } catch (error) {
    state.status = null;
    setBanner(error.message);
  }
  updateDetail();
}

function loadSettings() {
  elements.extractToggle.checked = localStorage.getItem("minerva.extract") !== "false";
  elements.rootFallbackToggle.checked = localStorage.getItem("minerva.rootFallback") === "true";
  elements.allFilesToggle.checked = localStorage.getItem("minerva.allFiles") === "true";
}

function saveSettings() {
  localStorage.setItem("minerva.destination", elements.destination.value.trim());
  localStorage.setItem("minerva.extract", String(elements.extractToggle.checked));
  localStorage.setItem("minerva.rootFallback", String(elements.rootFallbackToggle.checked));
  localStorage.setItem("minerva.allFiles", String(elements.allFilesToggle.checked));
  updateDetail();
}

/* Search */

function showEmptyResults(title, message) {
  elements.systemChips.replaceChildren();
  elements.results.innerHTML = `<div class="empty"><strong>${escapeHtml(title)}</strong>${escapeHtml(message)}</div>`;
}

function setResultsBusy(busy) {
  elements.results.setAttribute("aria-busy", String(busy));
}

function scheduleSearch(delay = 250) {
  clearTimeout(state.searchTimer);
  clearTimeout(state.searchPollTimer);
  state.searchPollTimer = null;
  ++state.searchRequest;
  state.searchAbort?.abort();
  state.searchTimer = setTimeout(() => search(elements.query.value), delay);
}

async function search(query, { polling = false } = {}) {
  clearTimeout(state.searchPollTimer);
  state.searchPollTimer = null;
  const trimmed = query.trim();
  if (trimmed.length < 3) {
    ++state.searchRequest;
    state.searchAbort?.abort();
    elements.searchCount.textContent = "";
    setResultsBusy(false);
    showEmptyResults("Search the archive", "Type at least three letters of a game's name.");
    return;
  }

  const requestId = polling ? state.searchRequest : ++state.searchRequest;
  if (!polling) {
    state.searchAbort?.abort();
    state.searchAbort = new AbortController();
  }
  setResultsBusy(true);

  const params = new URLSearchParams({
    q: trimmed,
    gamesOnly: String(!elements.allFilesToggle.checked),
  });

  try {
    const response = await apiFetch(`/api/search?${params}`, { signal: state.searchAbort?.signal });
    const payload = await response.json();
    if (requestId !== state.searchRequest) return;

    if (payload.indexing?.error) throw new Error(payload.indexing.error);
    if (!response.ok && response.status !== 202) throw new Error(payload.error || "Search failed");
    if (response.status === 202 || payload.indexing?.ready === false) {
      renderIndexing(payload.indexing || {});
      state.searchPollTimer = setTimeout(() => search(trimmed, { polling: true }), 2000);
      return;
    }
    renderResults(payload.results || [], payload.total || 0, payload.more);
  } catch (error) {
    if (error.name === "AbortError" || requestId !== state.searchRequest) return;
    elements.searchCount.textContent = "";
    showEmptyResults("Search could not finish", error.message);
  } finally {
    if (requestId === state.searchRequest && !state.searchPollTimer) setResultsBusy(false);
  }
}

function renderIndexing(indexing) {
  const processed = Number(indexing.processed || 0);
  const total = Number(indexing.total || 0);
  const percent = total ? Math.floor((processed / total) * 100) : 0;
  elements.searchCount.textContent = total ? `${percent}%` : "";
  elements.systemChips.replaceChildren();
  elements.results.innerHTML = `
    <div class="empty">
      <strong>${escapeHtml(indexing.stage || "Preparing the game catalog")}</strong>
      ${total ? `${formatBytes(processed)} of ${formatBytes(total)}. ` : ""}This happens once; search then works offline.
      <div class="progress" style="margin-top: 14px"><span style="width: ${percent}%"></span></div>
    </div>
  `;
}

function renderResults(games, total, more = false) {
  state.games = games;
  if (!games.length) {
    elements.searchCount.textContent = "";
    showEmptyResults("No games found", "Check the spelling, or try fewer words.");
    return;
  }
  const systems = new Set(games.map(systemName));
  if (state.systemFilter !== "all" && !systems.has(state.systemFilter)) state.systemFilter = "all";
  elements.searchCount.textContent = more
    ? `Top ${games.length} of ${total.toLocaleString()} files`
    : `${games.length} ${games.length === 1 ? "game" : "games"}`;
  renderChips();
  renderList();
}

function renderChips() {
  const counts = new Map();
  for (const game of state.games) counts.set(systemName(game), (counts.get(systemName(game)) || 0) + 1);
  const chips = [["all", `All ${state.games.length}`], ...[...counts].sort((a, b) => b[1] - a[1]).map(([name, count]) => [name, `${name} ${count}`])];
  elements.systemChips.replaceChildren(...chips.map(([value, label]) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `chip${value === state.systemFilter ? " active" : ""}`;
    chip.setAttribute("role", "tab");
    chip.setAttribute("aria-selected", String(value === state.systemFilter));
    chip.dataset.system = value;
    chip.textContent = label;
    chip.addEventListener("click", () => setSystemFilter(value));
    return chip;
  }));
}

function setSystemFilter(value) {
  state.systemFilter = value;
  renderChips();
  renderList();
  elements.systemChips.querySelector(".chip.active")?.scrollIntoView({ block: "nearest", inline: "nearest" });
}

function cycleSystemFilter(step) {
  const chips = [...elements.systemChips.querySelectorAll(".chip")];
  if (!chips.length) return;
  const index = chips.findIndex((chip) => chip.dataset.system === state.systemFilter);
  setSystemFilter(chips[(index + step + chips.length) % chips.length].dataset.system);
}

function visibleGames() {
  return state.systemFilter === "all"
    ? state.games
    : state.games.filter((game) => systemName(game) === state.systemFilter);
}

function renderList() {
  const games = visibleGames();
  if (!games.length) {
    showEmptyResults("No games for this system", "Choose another system above.");
    return;
  }
  const fragment = document.createDocumentFragment();
  for (const game of games) {
    const regions = gameRegions(game);
    const shown = regions.slice(0, 3).map((region) => `<span class="region">${escapeHtml(region)}</span>`).join("");
    const extra = regions.length > 3 ? `<span class="region">+${regions.length - 3}</span>` : "";
    const button = document.createElement("button");
    button.type = "button";
    button.className = `result${game === state.selectedGame ? " selected" : ""}`;
    button.innerHTML = `
      <span class="cover" data-cover-key="${escapeHtml(coverKey(game) || "")}"></span>
      <span>
        <span class="result-title">${escapeHtml(game.title)}</span>
        <span class="result-sub">${escapeHtml(systemName(game))} · ${
          game.verified ? `<span class="verified">Verified</span>` : escapeHtml(game.collection)
        }${game.variants.length > 1 ? ` · ${game.variants.length} versions` : ""}</span>
      </span>
      <span class="regions">${shown}${extra}</span>
      <span class="result-size">${escapeHtml(game.variants[0].size)}</span>
    `;
    paintCover(button.querySelector(".cover"), game);
    // Moving through results with the d-pad previews each game.
    button.addEventListener("focus", () => selectGame(game));
    button.addEventListener("click", () => {
      selectGame(game);
      elements.variantList.querySelector('[aria-checked="true"]')?.focus();
    });
    fragment.appendChild(button);
  }
  elements.results.replaceChildren(fragment);
}

/* Selected game */

function selectGame(game) {
  if (state.selectedGame === game) return;
  state.selectedGame = game;
  state.selectedVariant = game.variants[0];
  state.routeOverride = "";
  const games = visibleGames();
  elements.results.querySelectorAll(".result").forEach((button, index) => {
    button.classList.toggle("selected", games[index] === game);
  });

  elements.detailEmpty.hidden = true;
  elements.detailCard.hidden = false;
  elements.detailTitle.textContent = game.title;
  elements.detailSystem.textContent = game.platform;
  elements.detailSource.textContent = game.verified ? `Verified dump · ${game.collection}` : game.collection || "MiNERVA archive";
  elements.detailSource.classList.toggle("verified", game.verified);
  elements.detailCover.dataset.coverKey = coverKey(game) || "";
  paintCover(elements.detailCover, game);
  renderVariants();
  updateDetail();
}

function renderVariants() {
  const game = state.selectedGame;
  elements.variantList.replaceChildren(...game.variants.map((variant) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "variant";
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(variant === state.selectedVariant));
    button.innerHTML = `<span>${escapeHtml(variant.label)}</span><span class="muted">${escapeHtml(variant.size)}</span>`;
    button.title = variant.fileName;
    button.addEventListener("click", () => {
      state.selectedVariant = variant;
      elements.variantList.querySelectorAll(".variant").forEach((item, index) => {
        item.setAttribute("aria-checked", String(game.variants[index] === variant));
      });
      updateDetail();
      elements.downloadButton.focus();
    });
    return button;
  }));
}

function destinationFolder() {
  const root = elements.destination.value.trim().replace(/\/+$/, "");
  const folder = state.routeOverride || state.selectedGame?.route?.folder;
  if (folder) return { path: `${root}/${folder}`, known: true };
  if (elements.rootFallbackToggle.checked) return { path: root, known: true };
  return { path: "", known: false };
}

function legalAccepted() {
  return localStorage.getItem("minerva.legalAccepted") === "true";
}

function updateDetail() {
  if (!state.selectedGame) return;
  const destination = destinationFolder();
  const engineReady = Boolean(state.status?.capabilities?.torrentDownload?.ready);
  const hasRoot = Boolean(elements.destination.value.trim());

  elements.destinationSummary.textContent = destination.known
    ? destination.path
    : "This system has no EmuDeck folder";
  elements.destinationHint.hidden = destination.known && !state.routeOverride;
  elements.destinationHint.textContent = state.routeOverride
    ? "Custom folder for this download."
    : "Choose a folder, or turn on saving unrecognized systems in Settings.";
  elements.legalRow.hidden = legalAccepted();

  const variant = state.selectedVariant;
  elements.downloadButton.textContent = `Download · ${variant.size}`;
  let help = "";
  if (!engineReady) help = "The download engine is unavailable.";
  else if (!hasRoot) help = "Choose your EmuDeck ROMs folder in Settings.";
  else if (!destination.known) help = "Choose where this system's games go.";
  else if (!legalAccepted() && !elements.legalConfirm.checked) help = "Confirm the statement above to download.";
  elements.downloadHelp.textContent = help;
  elements.downloadButton.disabled = Boolean(help);
}

async function startDownload() {
  if (elements.downloadButton.disabled || !state.selectedVariant) return;
  if (elements.legalConfirm.checked) localStorage.setItem("minerva.legalAccepted", "true");
  const game = state.selectedGame;
  const variant = state.selectedVariant;
  const payload = {
    fullPath: variant.path,
    fileName: variant.fileName,
    title: `${game.title} (${variant.label})`,
    torrent: variant.torrentUrl || "",
    romsRoot: elements.destination.value.trim(),
    systemFolderOverride: state.routeOverride,
    allowRomsRootFallback: elements.rootFallbackToggle.checked,
    extract: elements.extractToggle.checked,
    legalConfirm: true,
  };
  elements.downloadButton.disabled = true;
  try {
    const response = await apiFetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "Could not start the download");
    state.activeJobId = body.id;
    pollQueue();
  } catch (error) {
    elements.downloadHelp.textContent = error.message;
  }
  updateDetail();
}

async function pickFolder(mode) {
  const button = mode === "root" ? elements.browseRootButton : elements.browseSubfolderButton;
  button.disabled = true;
  try {
    // Opens the system folder dialog; the request finishes when it closes.
    const response = await apiFetch("/api/pick-folder", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode,
        root: elements.destination.value.trim(),
        current: state.routeOverride || state.selectedGame?.route?.folder || "",
      }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not open the folder dialog");
    if (!payload.path) return;
    if (mode === "root") {
      elements.destination.value = payload.path;
      saveSettings();
    } else {
      state.routeOverride = payload.path;
      updateDetail();
    }
  } catch (error) {
    (mode === "root" ? elements.catalogInfo : elements.downloadHelp).textContent = error.message;
  } finally {
    button.disabled = false;
    button.focus({ preventScroll: true });
  }
}

/* Downloads */

async function pollQueue() {
  clearTimeout(state.pollTimer);
  state.pollTimer = null;
  try {
    const response = await apiFetch("/api/jobs");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Downloads are unavailable");
    state.jobs = payload.jobs || [];
    renderTray();
    if (!elements.downloadsDialog.hidden) renderDownloads();
    if (state.jobs.some((job) => job.status === "queued" || job.status === "running")) {
      state.pollTimer = setTimeout(pollQueue, document.hidden ? 5000 : 1000);
    }
  } catch (error) {
    elements.trayStatus.textContent = error.message;
  }
}

function trayJob() {
  return (
    state.jobs.find((job) => job.status === "running") ||
    state.jobs.find((job) => job.id === state.activeJobId) ||
    state.jobs.find((job) => job.status === "queued")
  );
}

function jobDetail(job) {
  if (job.status === "running" && job.totalBytes) {
    const remaining = job.rateBytes ? (job.totalBytes - job.downloadedBytes) / job.rateBytes : NaN;
    return [
      `${formatBytes(job.downloadedBytes)} of ${formatBytes(job.totalBytes)}`,
      job.rateBytes ? `${formatBytes(job.rateBytes)}/s` : "Finding peers",
      formatDuration(remaining),
    ].filter(Boolean).join(" · ");
  }
  if (job.status === "done") return job.outputs?.[0] ? `Saved to ${job.outputs[0]}` : "Completed";
  if (job.status === "error") return job.error || "Failed";
  return job.stage || jobStatusLabel(job.status);
}

function renderTray() {
  const active = state.jobs.filter((job) => job.status === "queued" || job.status === "running").length;
  elements.queueBadge.hidden = active === 0;
  elements.queueBadge.textContent = String(active);
  const job = trayJob();
  elements.tray.hidden = !job;
  if (!job) return;
  const queued = state.jobs.filter((item) => item.status === "queued" && item !== job).length;
  elements.tray.className = `tray ${job.status}`;
  elements.trayName.textContent = queued ? `${jobName(job)} (+${queued} queued)` : jobName(job);
  elements.trayStatus.textContent = jobDetail(job);
  const progress = job.status === "done" ? 100 : Math.max(0, Math.min(100, Number(job.progress) || 0));
  elements.trayProgress.style.width = `${progress}%`;
  elements.trayCancelButton.hidden = !["queued", "running"].includes(job.status);
}

async function cancelJob(jobId) {
  if (!jobId) return;
  await apiFetch(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST", body: "{}", headers: { "Content-Type": "application/json" } });
  pollQueue();
}

function renderDownloads() {
  const jobs = state.jobs;
  elements.downloadsActiveCount.textContent = String(jobs.filter((job) => jobMatchesFilter(job, "active")).length);
  elements.downloadsCompletedCount.textContent = String(jobs.filter((job) => job.status === "done").length);
  elements.downloadsIssueCount.textContent = String(jobs.filter((job) => jobMatchesFilter(job, "issues")).length);
  const filtered = [...jobs].reverse().filter((job) => jobMatchesFilter(job, state.downloadsFilter));
  if (!filtered.some((job) => job.id === state.selectedJobId)) state.selectedJobId = filtered[0]?.id || null;

  setHtml(elements.downloadsList, filtered.length
    ? filtered.map((job) => `
        <button class="download-item ${escapeHtml(job.status)}${job.id === state.selectedJobId ? " selected" : ""}" type="button" data-job="${escapeHtml(job.id)}">
          <span class="download-item-top">
            <strong>${escapeHtml(jobName(job))}</strong>
            <span class="status ${escapeHtml(job.status)}">${escapeHtml(jobStatusLabel(job.status))}</span>
          </span>
          <span class="progress"><span style="width: ${job.status === "done" ? 100 : Number(job.progress) || 0}%"></span></span>
        </button>`).join("")
    : `<div class="empty"><strong>Nothing here yet</strong>Downloads you start will be listed here.</div>`);

  const job = jobs.find((item) => item.id === state.selectedJobId);
  setHtml(elements.downloadsDetail, job ? `
      <h3>${escapeHtml(jobName(job))}</h3>
      <p class="muted">${escapeHtml(jobStatusLabel(job.status))} · Added ${escapeHtml(formatTimestamp(job.createdAt))}</p>
      <p class="${job.status === "error" ? "error-text" : ""}">${escapeHtml(jobDetail(job))}</p>
      ${(job.warnings || []).map((warning) => `<p class="hint">${escapeHtml(warning)}</p>`).join("")}
      ${["queued", "running"].includes(job.status) ? `<button class="button small" type="button" data-cancel-job="${escapeHtml(job.id)}">Cancel download</button>` : ""}
      <pre class="log">${escapeHtml((job.log || []).join("\n") || "No log entries.")}</pre>
    ` : "");
}

/* Overlays */

function openOverlay(overlay) {
  state.overlayReturnFocus = document.activeElement;
  overlay.hidden = false;
  if (overlay === elements.downloadsDialog) {
    elements.downloadsButton.setAttribute("aria-expanded", "true");
    renderDownloads();
    pollQueue();
  }
  overlay.querySelector("button")?.focus();
}

function closeOverlays() {
  const open = [elements.settingsDialog, elements.downloadsDialog].filter((overlay) => !overlay.hidden);
  if (!open.length) return false;
  for (const overlay of open) overlay.hidden = true;
  elements.downloadsButton.setAttribute("aria-expanded", "false");
  saveSettings();
  state.overlayReturnFocus?.focus?.({ preventScroll: true });
  return true;
}

/* Controller and keyboard navigation */

function openOverlayRoot() {
  return [elements.settingsDialog, elements.downloadsDialog].find((overlay) => !overlay.hidden) || null;
}

function focusTargets() {
  const root = openOverlayRoot() || document;
  return [...root.querySelectorAll("button:not([disabled]), input:not([disabled])")].filter(
    (element) => element.getClientRects().length > 0 && !element.closest("[hidden]"),
  );
}

function moveFocus(direction) {
  const targets = focusTargets();
  if (!targets.length) return;
  const active = targets.includes(document.activeElement) ? document.activeElement : null;
  if (!active) {
    (elements.results.querySelector(".result") || targets[0]).focus();
    return;
  }
  const from = active.getBoundingClientRect();
  const origin = { x: from.left + from.width / 2, y: from.top + from.height / 2 };
  let best = null;
  let bestScore = Infinity;
  for (const target of targets) {
    if (target === active) continue;
    const rect = target.getBoundingClientRect();
    const dx = rect.left + rect.width / 2 - origin.x;
    const dy = rect.top + rect.height / 2 - origin.y;
    const horizontal = direction === "left" || direction === "right";
    const along = horizontal ? dx : dy;
    const across = horizontal ? dy : dx;
    if ((direction === "up" || direction === "left") ? along >= -4 : along <= 4) continue;
    if (Math.abs(along) < Math.abs(across) * 0.35) continue;
    const score = Math.abs(along) * 3 + Math.abs(across);
    if (score < bestScore) {
      best = target;
      bestScore = score;
    }
  }
  if (!best) return;
  best.focus({ preventScroll: true });
  best.scrollIntoView({ block: "nearest", inline: "nearest" });
}

function goBack() {
  if (closeOverlays()) return;
  if (elements.detailCard.contains(document.activeElement)) {
    elements.results.querySelector(".result.selected")?.focus();
    return;
  }
  focusSearch();
}

function focusSearch() {
  closeOverlays();
  elements.query.focus({ preventScroll: true });
  elements.query.select();
}

function updateHints() {
  const active = document.activeElement;
  elements.hintAccept.textContent = active?.classList.contains("result")
    ? "Versions"
    : active === elements.downloadButton
      ? "Download"
      : "Select";
}

function handleKeys(event) {
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  const typing = event.target instanceof HTMLInputElement && event.target.type !== "checkbox";
  if (event.key === "Escape") {
    event.preventDefault();
    goBack();
    return;
  }
  if (event.key === "/" && !typing) {
    event.preventDefault();
    focusSearch();
    return;
  }
  const directions = { ArrowUp: "up", ArrowDown: "down", ArrowLeft: "left", ArrowRight: "right" };
  const direction = directions[event.key];
  if (!direction || (typing && (direction === "left" || direction === "right"))) return;
  event.preventDefault();
  moveFocus(direction);
}

const controllerInput = new ControllerInput({
  onDirection: moveFocus,
  onAccept: () => document.activeElement?.click(),
  onCancel: goBack,
  onSearch: focusSearch,
  onPrevious: () => cycleSystemFilter(-1),
  onNext: () => cycleSystemFilter(1),
});

function startGamepadNavigation() {
  const poller = createGamepadPoller({
    input: controllerInput,
    getGamepads: () => (navigator.getGamepads ? Array.from(navigator.getGamepads()).filter(Boolean) : []),
    isActive: () => !document.hidden && document.hasFocus(),
  });
  window.addEventListener("gamepaddisconnected", (event) => controllerInput.disconnect(event.gamepad.index));
  window.addEventListener("gamepadconnected", () => poller.start());
  window.addEventListener("blur", () => poller.stop());
  window.addEventListener("focus", () => poller.start());
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      poller.stop();
    } else {
      poller.start();
      // Downloads poll slowly while hidden; refresh at once when shown again.
      if (state.pollTimer) pollQueue();
    }
  });
  poller.start();
}

/* Wiring */

function bindEvents() {
  elements.query.addEventListener("input", () => {
    elements.clearQueryButton.hidden = !elements.query.value;
    scheduleSearch();
  });
  elements.query.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === "ArrowDown") {
      event.preventDefault();
      elements.results.querySelector(".result")?.focus();
    }
  });
  elements.clearQueryButton.addEventListener("click", () => {
    elements.query.value = "";
    elements.clearQueryButton.hidden = true;
    scheduleSearch(0);
    elements.query.focus();
  });
  elements.dismissSetupButton.addEventListener("click", () => setBanner(""));
  elements.settingsButton.addEventListener("click", () => openOverlay(elements.settingsDialog));
  elements.settingsCloseButton.addEventListener("click", closeOverlays);
  elements.downloadsButton.addEventListener("click", () => openOverlay(elements.downloadsDialog));
  elements.downloadsCloseButton.addEventListener("click", closeOverlays);
  elements.trayOpenButton.addEventListener("click", () => openOverlay(elements.downloadsDialog));
  elements.trayCancelButton.addEventListener("click", () => cancelJob(trayJob()?.id));
  elements.downloadButton.addEventListener("click", startDownload);
  elements.legalConfirm.addEventListener("change", updateDetail);
  elements.browseRootButton.addEventListener("click", () => pickFolder("root"));
  elements.browseSubfolderButton.addEventListener("click", () => pickFolder("subfolder"));
  elements.defaultDirButton.addEventListener("click", () => {
    elements.destination.value = state.status?.defaultDestination || "";
    saveSettings();
  });
  elements.destination.addEventListener("change", saveSettings);
  elements.extractToggle.addEventListener("change", saveSettings);
  elements.rootFallbackToggle.addEventListener("change", saveSettings);
  elements.allFilesToggle.addEventListener("change", () => {
    saveSettings();
    scheduleSearch(0);
  });
  for (const button of elements.downloadFilters) {
    button.addEventListener("click", () => {
      state.downloadsFilter = button.dataset.downloadFilter;
      for (const other of elements.downloadFilters) {
        other.classList.toggle("active", other === button);
        other.setAttribute("aria-selected", String(other === button));
      }
      renderDownloads();
    });
  }
  elements.downloadsList.addEventListener("click", (event) => {
    const item = event.target.closest("[data-job]");
    if (!item) return;
    state.selectedJobId = item.dataset.job;
    renderDownloads();
  });
  elements.downloadsDetail.addEventListener("click", (event) => {
    const button = event.target.closest("[data-cancel-job]");
    if (button) cancelJob(button.dataset.cancelJob);
  });
  document.addEventListener("keydown", handleKeys);
  document.addEventListener("focusin", updateHints);
}

async function init() {
  loadSettings();
  bindEvents();
  showEmptyResults("Search the archive", "Type at least three letters of a game's name.");
  await loadStatus();
  pollQueue();
  elements.query.focus();
  startGamepadNavigation();
}

init();
