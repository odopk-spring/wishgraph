const SAMPLE_HTML = `
<article>
  <h1>WishGraph Field Note</h1>
  <p>Complex AI-assisted projects fail when decisions live only inside chat history.</p>
  <p>A durable project memory should keep product intent, architecture boundaries, code maps, task specs, validation evidence, and handoff notes together.</p>
  <p>The human gives intent and judgment. The agent compiles that intent into scoped work, runs probes, and reports what changed.</p>
</article>`;

const STORAGE_KEY = "wishgraph-html-annotator-state";

const els = {
  fileInput: document.querySelector("#file-input"),
  sampleButton: document.querySelector("#sample-button"),
  pasteInput: document.querySelector("#paste-input"),
  pasteButton: document.querySelector("#paste-button"),
  clearButton: document.querySelector("#clear-button"),
  documentTitle: document.querySelector("#document-title"),
  statusLabel: document.querySelector("#status-label"),
  documentContent: document.querySelector("#document-content"),
  selectionPreview: document.querySelector("#selection-preview"),
  captureButton: document.querySelector("#capture-button"),
  noteForm: document.querySelector("#note-form"),
  noteInput: document.querySelector("#note-input"),
  saveNoteButton: document.querySelector("#save-note-button"),
  annotationList: document.querySelector("#annotation-list"),
  countLabel: document.querySelector("#count-label"),
  exportButton: document.querySelector("#export-button"),
  copyButton: document.querySelector("#copy-button"),
  exportOutput: document.querySelector("#export-output")
};

const state = {
  sourceName: "Untitled HTML",
  html: "",
  annotations: [],
  pendingRange: null,
  pendingText: "",
  nextId: 1
};

function setStatus(message) {
  els.statusLabel.textContent = message;
}

function selectionInsideDocument(selection) {
  if (!selection || selection.rangeCount === 0) return false;
  const range = selection.getRangeAt(0);
  return els.documentContent.contains(range.commonAncestorContainer);
}

function getCurrentSelection() {
  const selection = window.getSelection();
  if (!selectionInsideDocument(selection) || selection.isCollapsed) return null;
  const text = selection.toString().replace(/\s+/g, " ").trim();
  if (!text) return null;
  return {
    text,
    range: selection.getRangeAt(0).cloneRange()
  };
}

function setPendingRange(range, text, status = "Captured") {
  state.pendingRange = range;
  state.pendingText = text;
  els.selectionPreview.textContent = text.length > 140
    ? `${text.slice(0, 140)}...`
    : text;
  setStatus(status);
}

function updateSelectionPreview() {
  const selection = getCurrentSelection();
  if (!selection) {
    if (!state.pendingText) {
      els.selectionPreview.textContent = "Select text or tap a paragraph inside the document.";
    }
    return;
  }

  const preview = selection.text.length > 140
    ? `${selection.text.slice(0, 140)}...`
    : selection.text;
  els.selectionPreview.textContent = preview;
}

function removeRiskyMarkup(documentNode) {
  documentNode.querySelectorAll("script, iframe, object, embed, link, meta").forEach((node) => {
    node.remove();
  });

  documentNode.querySelectorAll("*").forEach((node) => {
    [...node.attributes].forEach((attr) => {
      const value = attr.value.trim().toLowerCase();
      if (attr.name.toLowerCase().startsWith("on")) node.removeAttribute(attr.name);
      if ((attr.name === "href" || attr.name === "src") && value.startsWith("javascript:")) {
        node.removeAttribute(attr.name);
      }
    });
  });
}

function parseHtml(rawHtml, sourceName) {
  const parser = new DOMParser();
  const parsed = parser.parseFromString(rawHtml, "text/html");
  removeRiskyMarkup(parsed);
  const title = parsed.querySelector("title")?.textContent?.trim()
    || parsed.querySelector("h1")?.textContent?.trim()
    || sourceName
    || "Untitled HTML";
  const bodyHtml = parsed.body?.innerHTML?.trim() || rawHtml;
  return { title, bodyHtml };
}

function loadHtml(rawHtml, sourceName = "Untitled HTML") {
  const parsed = parseHtml(rawHtml, sourceName);
  state.sourceName = sourceName;
  state.html = rawHtml;
  state.annotations = [];
  state.pendingRange = null;
  state.pendingText = "";
  state.nextId = 1;
  els.documentTitle.textContent = parsed.title;
  els.documentContent.innerHTML = parsed.bodyHtml;
  els.selectionPreview.textContent = "Select text or tap a paragraph inside the document.";
  els.noteInput.value = "";
  els.exportOutput.value = "";
  renderAnnotations();
  persistState();
  setStatus("Loaded");
}

function createAnnotation(range, quote, note) {
  const id = state.nextId;
  state.nextId += 1;
  const annotation = {
    id,
    sourceName: state.sourceName,
    quote,
    note,
    createdAt: new Date().toISOString()
  };

  wrapRange(range, id);
  state.annotations.push(annotation);
  state.pendingRange = null;
  state.pendingText = "";
  els.selectionPreview.textContent = "Select text or tap a paragraph inside the document.";
  els.noteInput.value = "";
  window.getSelection()?.removeAllRanges();
  renderAnnotations();
  persistState();
  setStatus("Saved");
}

function wrapRange(range, id) {
  const mark = document.createElement("mark");
  mark.className = "wg-highlight";
  mark.dataset.annotationId = String(id);

  try {
    range.surroundContents(mark);
  } catch {
    const content = range.extractContents();
    mark.append(content);
    range.insertNode(mark);
  }
}

function renderAnnotations() {
  els.countLabel.textContent = String(state.annotations.length);
  els.annotationList.innerHTML = "";

  for (const annotation of state.annotations) {
    const item = document.createElement("li");
    item.className = "annotation-item";

    const quote = document.createElement("blockquote");
    quote.textContent = annotation.quote;

    const note = document.createElement("p");
    note.textContent = annotation.note;

    const actions = document.createElement("div");
    actions.className = "annotation-actions";

    const jumpButton = document.createElement("button");
    jumpButton.type = "button";
    jumpButton.textContent = "Jump";
    jumpButton.addEventListener("click", () => activateAnnotation(annotation.id));

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "ghost-button delete-button";
    deleteButton.textContent = "Delete";
    deleteButton.addEventListener("click", () => deleteAnnotation(annotation.id));

    actions.append(jumpButton, deleteButton);
    item.append(quote, note, actions);
    els.annotationList.append(item);
  }
}

function activateAnnotation(id) {
  document.querySelectorAll(".wg-highlight.active").forEach((node) => {
    node.classList.remove("active");
  });
  const target = els.documentContent.querySelector(`[data-annotation-id="${id}"]`);
  if (!target) {
    setStatus("Highlight missing");
    return;
  }
  target.classList.add("active");
  target.scrollIntoView({ block: "center", behavior: "smooth" });
  setStatus("Focused");
}

function deleteAnnotation(id) {
  state.annotations = state.annotations.filter((annotation) => annotation.id !== id);
  const target = els.documentContent.querySelector(`[data-annotation-id="${id}"]`);
  if (target) {
    target.replaceWith(...target.childNodes);
  }
  renderAnnotations();
  persistState();
  setStatus("Deleted");
}

function exportAnnotations() {
  const payload = {
    sourceName: state.sourceName,
    exportedAt: new Date().toISOString(),
    annotations: state.annotations
  };
  els.exportOutput.value = JSON.stringify(payload, null, 2);
  setStatus("Exported");
  return els.exportOutput.value;
}

async function copyExport() {
  const payload = els.exportOutput.value || exportAnnotations();
  try {
    await navigator.clipboard.writeText(payload);
    setStatus("Copied");
  } catch {
    els.exportOutput.focus();
    els.exportOutput.select();
    setStatus("Select JSON");
  }
}

function persistState() {
  const persisted = {
    sourceName: state.sourceName,
    html: state.html,
    annotations: state.annotations,
    nextId: state.nextId
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(persisted));
}

function hydrateState() {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return;
  try {
    const persisted = JSON.parse(raw);
    if (!persisted.html) return;
    const parsed = parseHtml(persisted.html, persisted.sourceName);
    state.sourceName = persisted.sourceName || "Untitled HTML";
    state.html = persisted.html;
    state.annotations = Array.isArray(persisted.annotations) ? persisted.annotations : [];
    state.nextId = Number.isInteger(persisted.nextId) ? persisted.nextId : state.annotations.length + 1;
    els.documentTitle.textContent = parsed.title;
    els.documentContent.innerHTML = parsed.bodyHtml;
    renderAnnotations();
    setStatus("Restored");
  } catch {
    localStorage.removeItem(STORAGE_KEY);
  }
}

function clearAll() {
  localStorage.removeItem(STORAGE_KEY);
  state.sourceName = "Untitled HTML";
  state.html = "";
  state.annotations = [];
  state.pendingRange = null;
  state.pendingText = "";
  state.nextId = 1;
  els.documentTitle.textContent = "No document loaded";
  els.documentContent.innerHTML = '<p class="empty-state">Open the sample or load an HTML file to start annotating.</p>';
  els.selectionPreview.textContent = "Select text or tap a paragraph inside the document.";
  els.noteInput.value = "";
  els.exportOutput.value = "";
  renderAnnotations();
  setStatus("Ready");
}

els.fileInput.addEventListener("change", async (event) => {
  const file = event.target.files?.[0];
  if (!file) return;
  const text = await file.text();
  loadHtml(text, file.name);
});

els.sampleButton.addEventListener("click", async () => {
  try {
    const response = await fetch("samples/article.html");
    const html = response.ok ? await response.text() : SAMPLE_HTML;
    loadHtml(html, "sample/article.html");
  } catch {
    loadHtml(SAMPLE_HTML, "sample");
  }
});

els.pasteButton.addEventListener("click", () => {
  const pasted = els.pasteInput.value.trim();
  if (!pasted) {
    setStatus("Paste HTML first");
    return;
  }
  loadHtml(pasted, "pasted-html");
});

els.captureButton.addEventListener("click", () => {
  const selection = getCurrentSelection();
  if (!selection) {
    setStatus("No selection");
    return;
  }
  setPendingRange(selection.range, selection.text);
  els.noteInput.focus();
});

els.documentContent.addEventListener("click", (event) => {
  if (getCurrentSelection()) return;
  if (event.target.closest(".wg-highlight")) return;

  const block = event.target.closest("p, li, blockquote, h1, h2, h3, h4, h5, h6");
  if (!block || !els.documentContent.contains(block) || block.classList.contains("empty-state")) return;

  const text = block.textContent.replace(/\s+/g, " ").trim();
  if (!text) return;

  const range = document.createRange();
  range.selectNodeContents(block);
  setPendingRange(range, text, "Block staged");
});

els.noteForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const note = els.noteInput.value.trim();
  if (!state.pendingRange || !state.pendingText) {
    setStatus("Capture text first");
    return;
  }
  if (!note) {
    setStatus("Write a note");
    return;
  }
  createAnnotation(state.pendingRange, state.pendingText, note);
});

els.exportButton.addEventListener("click", exportAnnotations);
els.copyButton.addEventListener("click", copyExport);
els.clearButton.addEventListener("click", clearAll);
document.addEventListener("selectionchange", updateSelectionPreview);
hydrateState();
