const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;
const { getCurrentWindow } = window.__TAURI__.window;

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  inputPath: null,
  outputDir: null,
  running: false,
  doneOutputDir: null,
};

// ── DOM refs ───────────────────────────────────────────────────────────────
let dropZone, dropIdle, dropResult, dropName, dropType;
let btnPickFile, btnPickFolder, btnReset;
let btnOutput, outputPath;
let btnRun;
let progressSection, progressLog, btnOpenFolder;

// ── Lifecycle ──────────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", async () => {
  dropZone        = document.getElementById("drop-zone");
  dropIdle        = document.getElementById("drop-idle");
  dropResult      = document.getElementById("drop-result");
  dropName        = document.getElementById("drop-name");
  dropType        = document.getElementById("drop-type");
  btnPickFile     = document.getElementById("btn-pick-file");
  btnPickFolder   = document.getElementById("btn-pick-folder");
  btnReset        = document.getElementById("btn-reset");
  btnOutput       = document.getElementById("btn-output");
  outputPath      = document.getElementById("output-path");
  btnRun          = document.getElementById("btn-run");
  progressSection = document.getElementById("progress-section");
  progressLog     = document.getElementById("progress-log");
  btnOpenFolder   = document.getElementById("btn-open-folder");

  await bindDropZone();
  bindBrowseButtons();
  bindOutputPicker();
  bindRun();
  bindOpenFolder();
  syncUI();
});

// ── Drag & drop (API Tauri window — supporte fichiers ET dossiers) ─────────
async function bindDropZone() {
  await getCurrentWindow().onDragDropEvent(async (event) => {
    const { type, paths } = event.payload;

    if (type === "enter" || type === "over") {
      dropZone.classList.add("over");
      return;
    }

    if (type === "leave") {
      dropZone.classList.remove("over");
      return;
    }

    if (type === "drop" && paths?.length > 0) {
      dropZone.classList.remove("over");
      const path = paths[0];
      try {
        const kind = await invoke("get_path_kind", { path });
        setInput(path, kind);
      } catch (err) {
        console.error("get_path_kind:", err);
      }
    }
  });
}

// ── Boutons parcourir ──────────────────────────────────────────────────────
function bindBrowseButtons() {
  btnPickFile.addEventListener("click", async (e) => {
    e.stopPropagation();
    try {
      const path = await invoke("select_input_file");
      if (path) setInput(path, "fichier");
    } catch (err) {
      console.error("select_input_file:", err);
    }
  });

  btnPickFolder.addEventListener("click", async (e) => {
    e.stopPropagation();
    try {
      const path = await invoke("select_input_folder");
      if (path) setInput(path, "dossier");
    } catch (err) {
      console.error("select_input_folder:", err);
    }
  });

  btnReset.addEventListener("click", (e) => {
    e.stopPropagation();
    resetInput();
  });
}

function setInput(path, kind) {
  state.inputPath = path;
  const name = path.split("/").pop() || path;
  dropName.textContent = name;
  dropType.textContent = kind;
  dropIdle.classList.add("hidden");
  dropResult.classList.remove("hidden");
  syncUI();
}

function resetInput() {
  state.inputPath = null;
  dropResult.classList.add("hidden");
  dropIdle.classList.remove("hidden");
  syncUI();
}

// ── Output picker ──────────────────────────────────────────────────────────
function bindOutputPicker() {
  btnOutput.addEventListener("click", async () => {
    try {
      const dir = await invoke("select_output_dir");
      if (dir) {
        state.outputDir = dir;
        outputPath.textContent = dir;
        syncUI();
      }
    } catch (err) {
      console.error("select_output_dir:", err);
    }
  });
}

// ── Run ────────────────────────────────────────────────────────────────────
function bindRun() {
  btnRun.addEventListener("click", async () => {
    if (state.running) return;
    startRun();

    let unlisten;
    try {
      unlisten = await listen("packaging-progress", (event) => {
        appendLog(event.payload);
      });

      await invoke("run_packaging", {
        inputPath: state.inputPath,
        outputDir: state.outputDir,
      });
    } catch (err) {
      appendLog(`ERROR:${err}`);
    } finally {
      if (unlisten) unlisten();
      endRun();
    }
  });
}

function startRun() {
  state.running = true;
  state.doneOutputDir = null;
  btnRun.textContent = "En cours…";
  btnRun.disabled = true;
  btnOutput.disabled = true;
  progressLog.innerHTML = "";
  btnOpenFolder.classList.add("hidden");
  progressSection.classList.remove("hidden");
}

function endRun() {
  state.running = false;
  btnRun.textContent = "Générer le .exe";
  btnOutput.disabled = false;
  syncUI();
}

// ── Progress log ───────────────────────────────────────────────────────────
function appendLog(raw) {
  const colon = raw.indexOf(":");
  const status = colon >= 0 ? raw.slice(0, colon).toUpperCase() : "INFO";
  const message = colon >= 0 ? raw.slice(colon + 1) : raw;

  const line = document.createElement("div");
  line.className = "log-line " + statusClass(status);

  if (status === "STEP") {
    line.textContent = `▸ ${message}`;
  } else if (status === "DONE") {
    line.textContent = `✓ ${message}`;
    const parts = message.split("/");
    parts.pop();
    state.doneOutputDir = parts.join("/") || state.outputDir;
    btnOpenFolder.classList.remove("hidden");
  } else if (status === "ERROR") {
    line.textContent = `✗ ${message}`;
  } else {
    line.textContent = message;
  }

  progressLog.appendChild(line);
  progressLog.scrollTop = progressLog.scrollHeight;
}

function statusClass(status) {
  switch (status) {
    case "STEP":  return "log-step";
    case "DONE":  return "log-done";
    case "ERROR": return "log-error";
    default:      return "log-info";
  }
}

// ── Open folder ────────────────────────────────────────────────────────────
function bindOpenFolder() {
  btnOpenFolder.addEventListener("click", async () => {
    const dir = state.doneOutputDir ?? state.outputDir;
    if (!dir) return;
    try {
      await invoke("open_output_folder", { path: dir });
    } catch (err) {
      console.error("open_output_folder:", err);
    }
  });
}

// ── UI sync ────────────────────────────────────────────────────────────────
function syncUI() {
  btnRun.disabled = !(state.inputPath && state.outputDir && !state.running);
}
