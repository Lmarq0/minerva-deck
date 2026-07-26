const state = {
  status: null,
  selected: null,
  selectedRoute: null,
  selectedMetadata: null,
  searchTimer: null,
  searchPollTimer: null,
  pollTimer: null,
  activeJobId: null,
  jobs: [],
  selectedJobId: null,
  downloadsFilter: "all",
  downloadsPreviousFocus: null,
  searchRequest: 0,
  selectionRequest: 0,
  searchAbort: null,
  selectionAbort: null,
  gamepadButtons: new Map(),
  gamepadRepeat: { key: null, at: 0 },
  browse: { mode: null, current: "", parent: null, previousFocus: null },
};

const sessionToken =
  document.querySelector('meta[name="minerva-session-token"]')?.content || "";

function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-Minerva-Session", sessionToken);
  return fetch(url, { ...options, headers });
}

const elements = {
  setupStatus: document.getElementById("setupStatus"),
  setupStatusText: document.getElementById("setupStatusText"),
  setupBanner: document.getElementById("setupBanner"),
  setupBannerText: document.getElementById("setupBannerText"),
  dismissSetupButton: document.getElementById("dismissSetupButton"),
  downloadsButton: document.getElementById("downloadsButton"),
  queueBadge: document.getElementById("queueBadge"),
  query: document.getElementById("query"),
  gamesOnlyToggle: document.getElementById("gamesOnlyToggle"),
  formatFilter: document.getElementById("formatFilter"),
  searchCount: document.getElementById("searchCount"),
  results: document.getElementById("results"),
  selectionEmpty: document.getElementById("selectionEmpty"),
  selectionCard: document.getElementById("selectionCard"),
  clearButton: document.getElementById("clearButton"),
  platformBadge: document.getElementById("platformBadge"),
  selectedCollection: document.getElementById("selectedCollection"),
  selectedName: document.getElementById("selectedName"),
  selectedPath: document.getElementById("selectedPath"),
  regionFact: document.getElementById("regionFact"),
  formatFact: document.getElementById("formatFact"),
  sizeFact: document.getElementById("sizeFact"),
  destinationSummary: document.getElementById("destinationSummary"),
  destinationHint: document.getElementById("destinationHint"),
  routeStatus: document.getElementById("routeStatus"),
  advancedOptions: document.getElementById("advancedOptions"),
  destination: document.getElementById("destination"),
  defaultDirButton: document.getElementById("defaultDirButton"),
  browseRootButton: document.getElementById("browseRootButton"),
  routeOverride: document.getElementById("routeOverride"),
  autoRouteButton: document.getElementById("autoRouteButton"),
  browseSubfolderButton: document.getElementById("browseSubfolderButton"),
  extractToggle: document.getElementById("extractToggle"),
  rootFallbackToggle: document.getElementById("rootFallbackToggle"),
  legalConfirm: document.getElementById("legalConfirm"),
  downloadButton: document.getElementById("downloadButton"),
  downloadButtonLabel: document.getElementById("downloadButtonLabel"),
  downloadHelp: document.getElementById("downloadHelp"),
  activityDock: document.getElementById("activityDock"),
  activitySummary: document.getElementById("activitySummary"),
  activityDrawer: document.getElementById("activityDrawer"),
  activityIcon: document.getElementById("activityIcon"),
  activityDetail: document.getElementById("activityDetail"),
  jobStage: document.getElementById("jobStage"),
  jobPercent: document.getElementById("jobPercent"),
  progressTrack: document.getElementById("progressTrack"),
  progressBar: document.getElementById("progressBar"),
  queueList: document.getElementById("queueList"),
  outputs: document.getElementById("outputs"),
  jobLog: document.getElementById("jobLog"),
  downloadsDialog: document.getElementById("downloadsDialog"),
  downloadsCloseButton: document.getElementById("downloadsCloseButton"),
  downloadsRefreshButton: document.getElementById("downloadsRefreshButton"),
  downloadsActiveCount: document.getElementById("downloadsActiveCount"),
  downloadsCompletedCount: document.getElementById("downloadsCompletedCount"),
  downloadsIssueCount: document.getElementById("downloadsIssueCount"),
  downloadsList: document.getElementById("downloadsList"),
  downloadsDetail: document.getElementById("downloadsDetail"),
  downloadFilters: Array.from(document.querySelectorAll("[data-download-filter]")),
  browseDialog: document.getElementById("browseDialog"),
  browseTitle: document.getElementById("browseTitle"),
  browseCurrent: document.getElementById("browseCurrent"),
  browseList: document.getElementById("browseList"),
  browseCloseButton: document.getElementById("browseCloseButton"),
  browseParentButton: document.getElementById("browseParentButton"),
  browseSelectButton: document.getElementById("browseSelectButton"),
};

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
  return normalizePath(path).split("/").filter(Boolean).at(-1) || path || "";
}

function fileExtension(path) {
  const name = fileNameFromPath(path).toLowerCase();
  const compound = [".tar.gz", ".tar.bz2", ".tar.xz"];
  const matched = compound.find((suffix) => name.endsWith(suffix));
  if (matched) return matched.slice(1);
  const index = name.lastIndexOf(".");
  return index > -1 ? name.slice(index + 1) : "file";
}

function cleanGameTitle(value) {
  return String(value || "Selected game")
    .replace(/\.(tar\.(gz|bz2|xz)|[a-z0-9]{1,6})$/i, "")
    .replaceAll("_", " ")
    .replace(/\s+/g, " ")
    .trim();
}

function shortLabel(value, length = 34) {
  const text = String(value || "");
  return text.length > length ? `${text.slice(0, length - 1).trim()}…` : text;
}

function formatByteRate(value) {
  let rate = Number(value || 0);
  if (!Number.isFinite(rate) || rate <= 0) return "";
  const units = ["B/s", "KB/s", "MB/s", "GB/s"];
  let unit = units[0];
  for (const candidate of units) {
    unit = candidate;
    if (rate < 1024 || candidate === units.at(-1)) break;
    rate /= 1024;
  }
  return `${rate >= 100 ? rate.toFixed(0) : rate.toFixed(1)} ${unit}`;
}

function formatTimestamp(value) {
  if (!value) return "Not available";
  const date = new Date(Number(value));
  if (Number.isNaN(date.getTime())) return "Not available";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function jobName(job) {
  return (
    job?.payload?.fileName ||
    fileNameFromPath(job?.payload?.fullPath || job?.id || "") ||
    "Untitled download"
  );
}

function jobStatusLabel(status) {
  return {
    queued: "Queued",
    running: "Downloading",
    done: "Completed",
    error: "Failed",
    cancelled: "Cancelled",
  }[status] || "Unknown";
}

function jobMatchesFilter(job, filter) {
  if (filter === "active") return ["queued", "running"].includes(job.status);
  if (filter === "done") return job.status === "done";
  if (filter === "issues") return ["error", "cancelled"].includes(job.status);
  return true;
}

function formatLabel(result) {
  const extension = result.extension || fileExtension(result.path || result.fileName);
  const labels = {
    "7z": "7Z archive",
    zip: "ZIP archive",
    rar: "RAR archive",
    chd: "CHD image",
    iso: "ISO image",
    rvz: "RVZ image",
    wua: "WUA package",
    cia: "CIA package",
    nsp: "NSP package",
    xci: "XCI package",
  };
  return labels[extension.toLowerCase()] || `${extension.toUpperCase()} file`;
}

function platformGlyph(platform) {
  const words = String(platform || "Game").replace(/[^a-z0-9 ]/gi, " ").split(/\s+/).filter(Boolean);
  if (!words.length) return "GM";
  if (words.length === 1) return words[0].slice(0, 3);
  return words.slice(-2).map((word) => word[0]).join("");
}

function showEmptyResults(title, message, extra = "") {
  elements.results.innerHTML = `
    <div class="empty-note">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(message)}</span>
      ${extra}
    </div>
  `;
}

function setResultsBusy(busy) {
  elements.results.setAttribute("aria-busy", String(busy));
}

async function loadStatus() {
  try {
    const response = await apiFetch("/api/status");
    if (!response.ok) throw new Error("The local service is unavailable.");
    state.status = await response.json();
    const downloaderReady = Boolean(
      state.status.capabilities?.torrentDownload?.ready,
    );
    const archiveReady = Boolean(
      state.status.capabilities?.archiveExtraction?.ready,
    );
    const runtimeReady = downloaderReady && archiveReady;

    elements.setupStatus.classList.toggle("ready", runtimeReady);
    elements.setupStatusText.textContent = runtimeReady
      ? "Ready to download"
      : downloaderReady
        ? "Extraction unavailable"
        : "Engine unavailable";
    if (!runtimeReady && sessionStorage.getItem("minerva.dismissedSetup") !== "1") {
      elements.setupBanner.hidden = false;
      elements.setupBannerText.textContent =
        !downloaderReady
          ? "The embedded libtorrent engine could not start. Use an official build or install the project dependencies."
          : "The native libarchive library is missing. Use an official build, install the development dependency, or turn off automatic extraction.";
    } else {
      elements.setupBanner.hidden = true;
    }

    elements.destination.value =
      localStorage.getItem("minerva.destination") ||
      state.status.defaultDestination ||
      "";
  } catch (error) {
    state.status = null;
    elements.setupStatus.classList.remove("ready");
    elements.setupStatusText.textContent = "Service unavailable";
    elements.setupBanner.hidden = false;
    elements.setupBannerText.textContent = error.message;
  }
  updateDestinationSummary();
  updateDownloadButton();
}

function scheduleSearch(delay = 240) {
  clearTimeout(state.searchTimer);
  clearTimeout(state.searchPollTimer);
  state.searchTimer = setTimeout(() => search(elements.query.value), delay);
}

async function search(query, { polling = false } = {}) {
  const trimmed = query.trim();
  if (trimmed.length < 2) {
    state.searchAbort?.abort();
    elements.searchCount.textContent = "Ready";
    setResultsBusy(false);
    showEmptyResults("Search the archive", "Try a game title, a platform like SNES, or a region like USA.");
    return;
  }

  const requestId = polling ? state.searchRequest : ++state.searchRequest;
  if (!polling) {
    state.searchAbort?.abort();
    state.searchAbort = new AbortController();
  }

  setResultsBusy(true);
  elements.searchCount.textContent = polling ? "Preparing…" : "Searching…";
  if (!polling) {
    showEmptyResults("Looking through MiNERVA", "This should only take a moment.");
  }

  const params = new URLSearchParams({
    q: trimmed,
    gamesOnly: String(elements.gamesOnlyToggle.checked),
  });
  if (elements.formatFilter.value) params.set("format", elements.formatFilter.value);

  try {
    const response = await apiFetch(`/api/search?${params}`, {
      signal: state.searchAbort?.signal,
    });
    const payload = await response.json();
    if (requestId !== state.searchRequest) return;

    if (response.status === 202 || payload.indexing?.ready === false) {
      renderIndexing(payload.indexing || payload.loaded || {});
      state.searchPollTimer = setTimeout(() => search(trimmed, { polling: true }), 850);
      return;
    }
    if (!response.ok) throw new Error(payload.error || "Search failed");
    renderResults(payload.results || [], payload.total || 0);
  } catch (error) {
    if (error.name === "AbortError" || requestId !== state.searchRequest) return;
    elements.searchCount.textContent = "Unavailable";
    showEmptyResults("Search could not finish", error.message, "");
  } finally {
    if (requestId === state.searchRequest && !state.searchPollTimer) {
      setResultsBusy(false);
    }
  }
}

function renderIndexing(indexing) {
  const processed = Number(indexing.processed || indexing.count || 0);
  const detail = processed
    ? `${processed.toLocaleString()} archive entries prepared`
    : "MiNERVA Deck is preparing fast search for the first time.";
  elements.searchCount.textContent = indexing.stage || "Preparing";
  elements.results.innerHTML = `
    <div class="empty-note">
      <strong>Building your game catalog</strong>
      <span>${escapeHtml(detail)}</span>
      <div class="index-progress" aria-hidden="true"><span></span></div>
    </div>
  `;
}

function renderResults(results, total) {
  clearTimeout(state.searchPollTimer);
  state.searchPollTimer = null;
  setResultsBusy(false);
  elements.searchCount.textContent = total === 1 ? "1 result" : `${total.toLocaleString()} results`;
  if (!results.length) {
    showEmptyResults("No games found", "Try fewer words, a different platform, or turn off Games only.");
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const result of results) {
    const platform = result.platform || result.system || "Unknown system";
    const extension = result.extension || fileExtension(result.path || result.fileName);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "result-button";
    button.dataset.path = result.path;
    button.setAttribute("aria-pressed", String(state.selected?.path === result.path));
    if (state.selected?.path === result.path) button.classList.add("selected");
    button.innerHTML = `
      <span class="result-glyph" aria-hidden="true">${escapeHtml(platformGlyph(platform))}</span>
      <span class="result-copy">
        <span class="result-title">${escapeHtml(cleanGameTitle(result.fileName || fileNameFromPath(result.path)))}</span>
        <span class="result-meta">${escapeHtml([platform, result.region, result.collection].filter(Boolean).join(" · "))}</span>
      </span>
      <span class="result-format">${escapeHtml(extension)}</span>
    `;
    button.addEventListener("click", () => selectResult(result));
    fragment.appendChild(button);
  }
  elements.results.replaceChildren(fragment);
}

function selectResult(result) {
  state.selectionAbort?.abort();
  state.selectionAbort = new AbortController();
  const requestId = ++state.selectionRequest;
  state.selected = result;
  state.selectedRoute = result.route || null;
  state.selectedMetadata = null;

  document.querySelectorAll(".result-button").forEach((button) => {
    const selected = button.dataset.path === result.path;
    button.classList.toggle("selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  });

  elements.selectionEmpty.hidden = true;
  elements.selectionCard.hidden = false;
  const title = cleanGameTitle(result.fileName || fileNameFromPath(result.path));
  const platform = result.platform || result.system || "Detecting system…";
  elements.platformBadge.textContent = platform;
  elements.selectedCollection.textContent = result.collection || "MiNERVA archive";
  elements.selectedName.textContent = title;
  elements.selectedPath.textContent = normalizePath(result.path);
  elements.regionFact.hidden = !result.region;
  elements.regionFact.textContent = result.region || "";
  elements.formatFact.textContent = formatLabel(result);
  elements.sizeFact.textContent = result.size || "Size pending";
  elements.legalConfirm.checked = false;
  elements.routeOverride.value = "";
  elements.routeOverride.placeholder = result.route?.folder || "Automatically detected";

  updateDestinationSummary();
  updateDownloadButton();
  loadRoute(result.path, requestId);
  loadMetadata(result.path, requestId);

  if (window.matchMedia("(max-width: 900px)").matches) {
    elements.selectionCard.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function loadRoute(path, requestId) {
  if (state.selectedRoute?.folder) {
    updateDestinationSummary();
    updateDownloadButton();
    return;
  }
  try {
    const response = await apiFetch(`/api/route?path=${encodeURIComponent(path)}`, {
      signal: state.selectionAbort?.signal,
    });
    const payload = await response.json();
    if (requestId !== state.selectionRequest || state.selected?.path !== path) return;
    state.selectedRoute = response.ok ? payload.route : null;
    if (payload.route?.system) elements.platformBadge.textContent = payload.route.system;
    elements.routeOverride.placeholder = payload.route?.folder || "Enter a system folder";
  } catch {
    if (requestId !== state.selectionRequest) return;
    state.selectedRoute = null;
  }
  updateDestinationSummary();
  updateDownloadButton();
}

async function loadMetadata(path, requestId) {
  try {
    const response = await apiFetch(`/api/metadata?path=${encodeURIComponent(path)}`, {
      signal: state.selectionAbort?.signal,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Metadata unavailable");
    if (requestId !== state.selectionRequest || state.selected?.path !== path) return;
    state.selectedMetadata = payload;
    elements.sizeFact.textContent = payload.size || state.selected?.size || "Size unavailable";
  } catch {
    if (requestId !== state.selectionRequest || state.selected?.path !== path) return;
    state.selectedMetadata = null;
    elements.sizeFact.textContent = state.selected?.size || "Size unavailable";
  }
}

function clearSelection() {
  state.selectionAbort?.abort();
  state.selectionAbort = null;
  ++state.selectionRequest;
  state.selected = null;
  state.selectedRoute = null;
  state.selectedMetadata = null;
  elements.selectionCard.hidden = true;
  elements.selectionEmpty.hidden = false;
  elements.routeOverride.value = "";
  elements.legalConfirm.checked = false;
  document.querySelectorAll(".result-button").forEach((button) => {
    button.classList.remove("selected");
    button.setAttribute("aria-pressed", "false");
  });
  updateDestinationSummary();
  updateDownloadButton();
  elements.query.focus({ preventScroll: true });
}

function updateDestinationSummary() {
  const override = elements.routeOverride.value.trim();
  const fallback = elements.rootFallbackToggle.checked;
  elements.routeStatus.classList.remove("warning");

  if (!state.selected) {
    elements.destinationSummary.textContent = "Choose a game first";
    elements.destinationHint.textContent = "The best destination will be selected automatically.";
    elements.routeStatus.textContent = "Auto";
    return;
  }

  if (override) {
    elements.destinationSummary.textContent = `EmuDeck › ${override}`;
    elements.destinationHint.textContent = "Using your custom system subfolder.";
    elements.routeStatus.textContent = "Custom";
    return;
  }

  if (state.selectedRoute?.folder) {
    elements.destinationSummary.textContent = `EmuDeck › ${state.selectedRoute.system || state.selectedRoute.folder}`;
    elements.destinationHint.textContent = state.selectedRoute.folder;
    elements.routeStatus.textContent = "Auto";
    return;
  }

  if (fallback) {
    elements.destinationSummary.textContent = "EmuDeck ROMs root";
    elements.destinationHint.textContent = "Using the main folder fallback.";
    elements.routeStatus.textContent = "Fallback";
    elements.routeStatus.classList.add("warning");
    return;
  }

  elements.destinationSummary.textContent = "System folder not recognized";
  elements.destinationHint.textContent = "Choose a subfolder or enable the ROMs root fallback.";
  elements.routeStatus.textContent = "Action needed";
  elements.routeStatus.classList.add("warning");
}

function updateDownloadButton() {
  const downloaderReady = Boolean(
    state.status?.capabilities?.torrentDownload?.ready,
  );
  const archiveReady = Boolean(
    state.status?.capabilities?.archiveExtraction?.ready,
  );
  const hasDestination = Boolean(elements.destination.value.trim());
  const hasRoute = Boolean(
    elements.routeOverride.value.trim() ||
    state.selectedRoute?.folder ||
    elements.rootFallbackToggle.checked,
  );
  const legal = elements.legalConfirm.checked;
  const enabled = Boolean(
    state.selected && downloaderReady && hasDestination && hasRoute && legal,
  );
  elements.downloadButton.disabled = !enabled;

  const title = cleanGameTitle(state.selected?.fileName || fileNameFromPath(state.selected?.path || ""));
  elements.downloadButtonLabel.textContent = elements.rootFallbackToggle.checked
    ? `Download ${shortLabel(title || "game", 27)} to ROMs root`
    : `Add ${shortLabel(title || "game", 31)} to EmuDeck`;

  if (!state.selected) {
    elements.downloadHelp.textContent = "Select a game to continue.";
  } else if (!downloaderReady) {
    elements.downloadHelp.textContent = "The embedded download engine is unavailable.";
  } else if (!hasDestination) {
    elements.downloadHelp.textContent = "Choose your EmuDeck ROMs root in Advanced options.";
  } else if (!hasRoute) {
    elements.downloadHelp.textContent = "Choose a system subfolder or enable the ROMs root fallback.";
  } else if (!legal) {
    elements.downloadHelp.textContent = "Confirm that you have the right to use this file.";
  } else if (!archiveReady && elements.extractToggle.checked) {
    elements.downloadHelp.textContent =
      "Archive extraction is unavailable; turn it off or use an official build.";
  } else {
    elements.downloadHelp.textContent = "Ready to download and place in your library.";
  }
}

async function startDownload() {
  if (elements.downloadButton.disabled || !state.selected) return;
  const destination = elements.destination.value.trim();
  localStorage.setItem("minerva.destination", destination);
  elements.downloadButton.disabled = true;
  setJobUi({
    status: "queued",
    stage: "Adding to download queue",
    progress: 0,
    payload: { fileName: state.selected.fileName },
    log: [],
  });

  const payload = {
    fullPath: state.selected.path,
    fileName: state.selected.fileName || fileNameFromPath(state.selected.path),
    torrent: state.selectedMetadata?.torrentUrl || "",
    romsRoot: destination,
    systemFolderOverride: elements.routeOverride.value.trim(),
    allowRomsRootFallback: elements.rootFallbackToggle.checked,
    extract: elements.extractToggle.checked,
    legalConfirm: elements.legalConfirm.checked,
  };

  try {
    const response = await apiFetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "Could not start download");
    state.activeJobId = body.id;
    setActivityExpanded(true);
    pollQueue();
  } catch (error) {
    setJobUi({
      status: "error",
      stage: "Download could not start",
      error: error.message,
      payload,
      log: [error.message],
    });
  }
  updateDownloadButton();
}

async function pollQueue() {
  clearTimeout(state.pollTimer);
  try {
    const response = await apiFetch("/api/jobs");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Download queue unavailable");
    const jobs = payload.jobs || [];
    state.jobs = jobs;
    setQueueUi(jobs);
    setDownloadsUi(jobs);
    const active =
      jobs.find((job) => job.status === "running") ||
      jobs.find((job) => job.id === state.activeJobId) ||
      jobs.at(-1);
    if (active) setJobUi(active);
    else setIdleJobUi();

    if (jobs.some((job) => job.status === "queued" || job.status === "running")) {
      state.pollTimer = setTimeout(pollQueue, 1000);
    }
  } catch (error) {
    setJobUi({ status: "error", stage: "Download service unavailable", error: error.message, log: [error.message] });
  }
  updateDownloadButton();
}

function setIdleJobUi() {
  elements.jobStage.textContent = "Ready when you are";
  elements.activityDetail.textContent = "Downloads and completed files will appear here.";
  elements.jobPercent.textContent = "—";
  elements.progressBar.style.width = "0%";
  elements.progressTrack.setAttribute("aria-valuenow", "0");
  elements.activityIcon.textContent = "↓";
  elements.activityIcon.className = "activity-icon";
}

function setQueueUi(jobs) {
  const activeCount = jobs.filter((job) => job.status === "queued" || job.status === "running").length;
  elements.queueBadge.hidden = activeCount === 0;
  elements.queueBadge.textContent = String(activeCount);
  if (!jobs.length) {
    elements.queueList.innerHTML = `<div class="empty-note"><span>No download history yet.</span></div>`;
    return;
  }
  elements.queueList.innerHTML = jobs.slice(-8).reverse().map((job) => {
    const name = jobName(job);
    const progress = Number.isFinite(job.progress) ? ` ${job.progress}%` : "";
    return `<button class="queue-item ${escapeHtml(job.status)}" type="button" data-download-job="${escapeHtml(job.id)}">
      <span>${escapeHtml(name)}</span>
      <strong>${escapeHtml(jobStatusLabel(job.status))}${escapeHtml(progress)}</strong>
    </button>`;
  }).join("");
}

function setDownloadsUi(jobs) {
  const activeCount = jobs.filter((job) => ["queued", "running"].includes(job.status)).length;
  const completedCount = jobs.filter((job) => job.status === "done").length;
  const issueCount = jobs.filter((job) => ["error", "cancelled"].includes(job.status)).length;
  elements.downloadsActiveCount.textContent = String(activeCount);
  elements.downloadsCompletedCount.textContent = String(completedCount);
  elements.downloadsIssueCount.textContent = String(issueCount);

  const filteredJobs = [...jobs]
    .reverse()
    .filter((job) => jobMatchesFilter(job, state.downloadsFilter));
  if (!filteredJobs.some((job) => job.id === state.selectedJobId)) {
    state.selectedJobId =
      filteredJobs.find((job) => ["running", "queued"].includes(job.status))?.id ||
      filteredJobs[0]?.id ||
      null;
  }

  if (!filteredJobs.length) {
    const message =
      jobs.length && state.downloadsFilter !== "all"
        ? "No downloads match this filter."
        : "Your downloads will appear here and remain available after restarting MiNERVA Deck.";
    elements.downloadsList.innerHTML = `
      <div class="empty-note">
        <strong>No download history yet</strong>
        <span>${escapeHtml(message)}</span>
      </div>
    `;
  } else {
    elements.downloadsList.innerHTML = filteredJobs.map((job) => {
      const progress = Number.isFinite(job.progress)
        ? Math.max(0, Math.min(100, Number(job.progress)))
        : 0;
      return `
        <button
          class="download-history-item${job.id === state.selectedJobId ? " selected" : ""}"
          type="button"
          data-download-job="${escapeHtml(job.id)}"
          aria-pressed="${job.id === state.selectedJobId}"
        >
          <span class="download-history-primary">
            <strong>${escapeHtml(jobName(job))}</strong>
            <span class="download-status ${escapeHtml(job.status)}">${escapeHtml(jobStatusLabel(job.status))}</span>
          </span>
          <span class="download-history-secondary">
            <span>${escapeHtml(job.stage || jobStatusLabel(job.status))}</span>
            <span>${escapeHtml(formatTimestamp(job.updatedAt))}</span>
          </span>
          <span class="download-mini-progress" aria-hidden="true">
            <span style="width: ${progress}%"></span>
          </span>
        </button>
      `;
    }).join("");
  }
  renderDownloadDetail(jobs.find((job) => job.id === state.selectedJobId));
}

function renderDownloadDetail(job) {
  if (!job) {
    elements.downloadsDetail.innerHTML = `
      <div class="download-detail-empty">
        <strong>No download selected</strong>
        <span>Choose an item to see its destination, progress, warnings, and technical log.</span>
      </div>
    `;
    return;
  }

  const progress = Number.isFinite(job.progress)
    ? Math.max(0, Math.min(100, Number(job.progress)))
    : 0;
  const rate = formatByteRate(job.rateBytes);
  const peers = Number(job.peers || 0);
  const progressLabel =
    job.status === "running" && rate
      ? `${rate} · ${peers} ${peers === 1 ? "peer" : "peers"}`
      : job.stage || jobStatusLabel(job.status);
  const outputs = (job.outputs || [])
    .map((path) => `<div>${escapeHtml(path)}</div>`)
    .join("");
  const warnings = (job.warnings || [])
    .map((warning) => `<p class="download-message">${escapeHtml(warning)}</p>`)
    .join("");
  const message = job.error
    ? `<p class="download-message error">${escapeHtml(job.error)}</p>`
    : warnings;
  const log = (job.log || []).join("\n");

  elements.downloadsDetail.innerHTML = `
    <div class="download-detail-head">
      <div>
        <h3>${escapeHtml(jobName(job))}</h3>
        <div class="download-detail-meta">
          <span>Added ${escapeHtml(formatTimestamp(job.createdAt))}</span>
          <span>${job.finishedAt ? `Finished ${escapeHtml(formatTimestamp(job.finishedAt))}` : "Not finished"}</span>
        </div>
      </div>
      <span class="download-status ${escapeHtml(job.status)}">${escapeHtml(jobStatusLabel(job.status))}</span>
    </div>
    <div class="download-detail-progress">
      <div class="download-detail-progress-copy">
        <span>${escapeHtml(progressLabel)}</span>
        <span>${Number.isFinite(job.progress) ? `${progress}%` : "—"}</span>
      </div>
      <div class="download-mini-progress" role="progressbar" aria-label="Selected download progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${progress}">
        <span style="width: ${progress}%"></span>
      </div>
    </div>
    ${message}
    ${outputs ? `
      <section class="download-detail-section">
        <h4>Saved files</h4>
        <div class="download-path-list">${outputs}</div>
      </section>
    ` : ""}
    <section class="download-detail-section">
      <h4>Technical log</h4>
      <pre class="job-log">${escapeHtml(log || "No technical log entries.")}</pre>
    </section>
  `;
}

function setDownloadsFilter(filter) {
  state.downloadsFilter = filter;
  for (const button of elements.downloadFilters) {
    const selected = button.dataset.downloadFilter === filter;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
  }
  setDownloadsUi(state.jobs);
}

function openDownloads(jobId = null) {
  if (jobId) state.selectedJobId = jobId;
  if (elements.downloadsDialog.hidden) {
    state.downloadsPreviousFocus = document.activeElement;
    elements.downloadsDialog.hidden = false;
    document.body.classList.add("downloads-open");
  }
  elements.downloadsButton.setAttribute("aria-expanded", "true");
  setDownloadsUi(state.jobs);
  pollQueue();
  requestAnimationFrame(() => {
    const selected = elements.downloadsList.querySelector(".download-history-item.selected");
    (selected || elements.downloadsCloseButton).focus();
  });
}

function closeDownloads() {
  if (elements.downloadsDialog.hidden) return;
  elements.downloadsDialog.hidden = true;
  document.body.classList.remove("downloads-open");
  resetDownloadsState();
}

function resetDownloadsState() {
  elements.downloadsButton.setAttribute("aria-expanded", "false");
  const previous = state.downloadsPreviousFocus;
  state.downloadsPreviousFocus = null;
  if (previous instanceof HTMLElement) previous.focus({ preventScroll: true });
}

function setJobUi(job) {
  const progress = Number.isFinite(job.progress) ? Math.max(0, Math.min(100, job.progress)) : 0;
  const name = job.payload?.fileName || fileNameFromPath(job.payload?.fullPath || "");
  const transferRate = formatByteRate(job.rateBytes);
  const peerLabel = Number(job.peers) === 1 ? "1 peer" : `${Number(job.peers || 0)} peers`;
  const transferDetail =
    job.status === "running" && transferRate
      ? `${transferRate} · ${peerLabel}`
      : "";
  elements.jobStage.textContent = job.stage || "Working";
  elements.activityDetail.textContent =
    job.error ||
    job.warnings?.[0] ||
    transferDetail ||
    name ||
    "Preparing your download.";
  elements.jobPercent.textContent = Number.isFinite(job.progress) ? `${progress}%` : "—";
  elements.progressBar.style.width = `${progress}%`;
  elements.progressTrack.setAttribute("aria-valuenow", String(progress));
  elements.outputs.innerHTML = (job.outputs || []).map((item) => `<div>Saved to ${escapeHtml(item)}</div>`).join("");
  if (job.warnings?.length) {
    elements.outputs.innerHTML += job.warnings
      .map((warning) => `<div class="output-warning">${escapeHtml(warning)}</div>`)
      .join("");
  }
  elements.jobLog.textContent = (job.log || []).join("\n");
  elements.jobLog.scrollTop = elements.jobLog.scrollHeight;

  elements.activityIcon.className = "activity-icon";
  if (job.status === "done") {
    elements.activityIcon.textContent = "✓";
    elements.activityIcon.classList.add("done");
  } else if (job.status === "error") {
    elements.activityIcon.textContent = "!";
    elements.activityIcon.classList.add("error");
  } else {
    elements.activityIcon.textContent = "↓";
  }
}

function setActivityExpanded(expanded) {
  elements.activityDrawer.hidden = !expanded;
  elements.activitySummary.setAttribute("aria-expanded", String(expanded));
}

async function openBrowser(mode) {
  state.browse.mode = mode;
  state.browse.previousFocus = document.activeElement;
  elements.browseTitle.textContent = mode === "root" ? "EmuDeck ROMs root" : "System subfolder";
  elements.browseDialog.showModal();
  await browseTo(mode === "root" ? elements.destination.value : elements.routeOverride.value);
  elements.browseSelectButton.focus();
}

function closeBrowser() {
  if (elements.browseDialog.open) elements.browseDialog.close();
}

function resetBrowserState() {
  const previous = state.browse.previousFocus;
  state.browse = { mode: null, current: "", parent: null, previousFocus: null };
  if (previous?.focus) previous.focus({ preventScroll: true });
}

async function browseTo(path) {
  const mode = state.browse.mode;
  if (!mode) return;
  elements.browseList.innerHTML = `<div class="empty-note"><span>Loading folders…</span></div>`;
  const params = new URLSearchParams({ mode, path: path || "" });
  if (mode === "subfolder") params.set("root", elements.destination.value.trim());
  try {
    const response = await apiFetch(`/api/browse?${params}`);
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Could not browse this folder");
    renderBrowse(payload);
  } catch (error) {
    elements.browseList.innerHTML = `<div class="empty-note error"><span>${escapeHtml(error.message)}</span></div>`;
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
    elements.browseList.innerHTML = `<div class="empty-note"><span>No child folders here.</span></div>`;
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
  }
  updateDestinationSummary();
  updateDownloadButton();
  closeBrowser();
}

function bindEvents() {
  elements.query.addEventListener("input", () => scheduleSearch());
  elements.gamesOnlyToggle.addEventListener("change", () => scheduleSearch(0));
  elements.formatFilter.addEventListener("change", () => scheduleSearch(0));
  elements.clearButton.addEventListener("click", clearSelection);
  elements.legalConfirm.addEventListener("change", updateDownloadButton);
  elements.extractToggle.addEventListener("change", updateDownloadButton);
  elements.rootFallbackToggle.addEventListener("change", () => {
    updateDestinationSummary();
    updateDownloadButton();
  });
  elements.destination.addEventListener("input", updateDownloadButton);
  elements.routeOverride.addEventListener("input", () => {
    updateDestinationSummary();
    updateDownloadButton();
  });
  elements.defaultDirButton.addEventListener("click", () => {
    elements.destination.value = state.status?.defaultDestination || "";
    updateDownloadButton();
  });
  elements.autoRouteButton.addEventListener("click", () => {
    elements.routeOverride.value = "";
    updateDestinationSummary();
    updateDownloadButton();
  });
  elements.browseRootButton.addEventListener("click", () => openBrowser("root"));
  elements.browseSubfolderButton.addEventListener("click", () => openBrowser("subfolder"));
  elements.downloadButton.addEventListener("click", startDownload);
  elements.dismissSetupButton.addEventListener("click", () => {
    sessionStorage.setItem("minerva.dismissedSetup", "1");
    elements.setupBanner.hidden = true;
  });
  elements.activitySummary.addEventListener("click", () => {
    setActivityExpanded(elements.activitySummary.getAttribute("aria-expanded") !== "true");
  });
  elements.downloadsButton.addEventListener("click", () => openDownloads());
  elements.downloadsCloseButton.addEventListener("click", closeDownloads);
  elements.downloadsRefreshButton.addEventListener("click", pollQueue);
  elements.downloadsDialog.addEventListener("click", (event) => {
    if (event.target === elements.downloadsDialog) closeDownloads();
  });
  for (const button of elements.downloadFilters) {
    button.addEventListener("click", () => setDownloadsFilter(button.dataset.downloadFilter));
  }
  elements.downloadsList.addEventListener("click", (event) => {
    const item = event.target.closest("[data-download-job]");
    if (!item) return;
    state.selectedJobId = item.dataset.downloadJob;
    setDownloadsUi(state.jobs);
  });
  elements.queueList.addEventListener("click", (event) => {
    const item = event.target.closest("[data-download-job]");
    if (!item) return;
    openDownloads(item.dataset.downloadJob);
  });
  elements.browseCloseButton.addEventListener("click", closeBrowser);
  elements.browseDialog.addEventListener("close", resetBrowserState);
  elements.browseParentButton.addEventListener("click", () => {
    if (state.browse.parent !== null) browseTo(state.browse.parent);
  });
  elements.browseSelectButton.addEventListener("click", selectBrowsedPath);
  document.addEventListener("keydown", handleControllerKeyboard);
}

async function init() {
  bindEvents();
  showEmptyResults("Search the archive", "Try a game title, a platform like SNES, or a region like USA.");
  await loadStatus();
  pollQueue();
  requestAnimationFrame(() => {
    elements.query.focus();
    startGamepadNavigation();
  });
}

function controllerTargets() {
  const root = !elements.downloadsDialog.hidden
    ? elements.downloadsDialog
    : elements.browseDialog.open
      ? elements.browseDialog
      : document;
  return Array.from(
    root.querySelectorAll("button:not([disabled]), input:not([disabled]), select:not([disabled]), summary"),
  ).filter((element) => {
    const style = window.getComputedStyle(element);
    return style.display !== "none" && style.visibility !== "hidden" && element.getClientRects().length > 0;
  });
}

function ensureControllerFocus() {
  const targets = controllerTargets();
  if (targets.length && !targets.includes(document.activeElement)) targets[0].focus();
}

function handleControllerKeyboard(event) {
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  if (event.key === "Escape") {
    if (!elements.downloadsDialog.hidden) {
      closeDownloads();
      return;
    }
    if (elements.browseDialog.open) {
      closeBrowser();
      return;
    }
  }

  const arrows = {
    ArrowUp: "up",
    ArrowDown: "down",
    ArrowLeft: "left",
    ArrowRight: "right",
  };
  if (!arrows[event.key]) return;
  if (event.target instanceof HTMLSelectElement) return;
  const isTextInput = event.target instanceof HTMLInputElement && event.target.type !== "checkbox";
  if (isTextInput && (event.key === "ArrowLeft" || event.key === "ArrowRight")) return;
  event.preventDefault();
  moveControllerFocus(arrows[event.key]);
}

function moveControllerFocus(direction) {
  const targets = controllerTargets();
  if (!targets.length) return;
  const active = targets.includes(document.activeElement) ? document.activeElement : targets[0];
  const currentCenter = rectCenter(active.getBoundingClientRect());
  let best = null;
  let bestScore = Number.POSITIVE_INFINITY;

  for (const target of targets) {
    if (target === active) continue;
    const center = rectCenter(target.getBoundingClientRect());
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
    const offset = direction === "up" || direction === "left" ? -1 : 1;
    best = targets[Math.max(0, Math.min(targets.length - 1, index + offset))];
  }
  best.focus({ preventScroll: true });
  best.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
}

function rectCenter(rect) {
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
}

function isInDirection(direction, dx, dy) {
  if (direction === "up") return dy < -4 && Math.abs(dy) >= Math.abs(dx) * 0.35;
  if (direction === "down") return dy > 4 && Math.abs(dy) >= Math.abs(dx) * 0.35;
  if (direction === "left") return dx < -4 && Math.abs(dx) >= Math.abs(dy) * 0.35;
  return dx > 4 && Math.abs(dx) >= Math.abs(dy) * 0.35;
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

  if (direction && shouldRepeat(direction)) moveControllerFocus(direction);
  if (!direction) state.gamepadRepeat = { key: null, at: 0 };

  if (buttonPressedOnce(pad, 0, "a")) {
    ensureControllerFocus();
    document.activeElement?.click();
  }
  if (buttonPressedOnce(pad, 1, "b")) {
    if (!elements.downloadsDialog.hidden) closeDownloads();
    else if (elements.browseDialog.open) closeBrowser();
    else if (elements.advancedOptions.open) elements.advancedOptions.open = false;
    else elements.query.focus({ preventScroll: true });
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
  const delay = state.gamepadRepeat.key === key ? 130 : 260;
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

init();
