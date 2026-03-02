/* BrainC UI — PHI369 Labs · v1.0.0 */

const API_BASE = "http://localhost:8000";

// ── Auth state ───────────────────────────────────────────────────────────────
let authToken = sessionStorage.getItem("braincToken") || "";
let refreshToken = sessionStorage.getItem("braincRefreshToken") || "";
let currentUser = null;

try {
  const stored = sessionStorage.getItem("braincUser");
  if (stored) currentUser = JSON.parse(stored);
} catch (_) {}

sessionStorage.removeItem("braincToken");
sessionStorage.removeItem("braincRefreshToken");
sessionStorage.removeItem("braincUser");

// ── DOM refs ─────────────────────────────────────────────────────────────────
const chatContainer = document.getElementById("chat-container");
const emptyState = document.getElementById("empty-state");
const inputForm = document.getElementById("input-form");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const clearBtn = document.getElementById("clear-btn");
const statusText = document.getElementById("status-text");
const newChatBtn = document.getElementById("new-chat-btn");
const convList = document.getElementById("conv-list");
const notesList = document.getElementById("notes-list");
const newNoteBtn = document.getElementById("new-note-btn");
const toolsToggle = document.getElementById("tools-toggle");
const toolsBadge = document.getElementById("tools-badge");
const toolPanel = document.getElementById("tool-panel");
const toolPanelToggle = document.getElementById("tool-panel-toggle");
const toolPanelName = document.getElementById("tool-panel-name");
const toolPanelBody = document.getElementById("tool-panel-body");
const toolPanelResult = document.getElementById("tool-panel-result");
const noteModal = document.getElementById("note-modal");
const noteTitleInput = document.getElementById("note-title-input");
const noteContentInput = document.getElementById("note-content-input");
const noteSaveBtn = document.getElementById("note-save-btn");
const noteCancelBtn = document.getElementById("note-cancel-btn");
const noteModalClose = document.getElementById("note-modal-close");
const userMenu = document.getElementById("user-menu");
const userDisplay = document.getElementById("user-display");
const adminLink = document.getElementById("admin-link");
const logoutBtn = document.getElementById("logout-btn");
const connDot = document.getElementById("conn-dot");
const connLabel = document.getElementById("conn-label");
const queueDepthEl = document.getElementById("queue-depth");
const queueDepthIndicator = document.getElementById("queue-depth-indicator");
const modelNameDisplay = document.getElementById("model-name-display");
const modelBtn = document.getElementById("model-btn");
const modelDropdown = document.getElementById("model-dropdown");
const modelList = document.getElementById("model-list");

let isStreaming = false;
let currentConversationId = "default";

// ── Auth helpers ──────────────────────────────────────────────────────────────

function authHeaders() {
  return {
    "Content-Type": "application/json",
    ...(authToken ? { "Authorization": `Bearer ${authToken}` } : {}),
  };
}

function redirectToLogin() {
  window.location.replace("/login");
}

async function handleUnauthorized() {
  if (refreshToken) {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (res.ok) {
        const data = await res.json();
        authToken = data.access_token;
        refreshToken = data.refresh_token;
        return true;
      }
    } catch (_) {}
  }
  redirectToLogin();
  return false;
}

async function apiFetch(path, options = {}) {
  const headers = { ...authHeaders(), ...(options.headers || {}) };
  delete options.headers;
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (res.status === 401) {
    const ok = await handleUnauthorized();
    if (ok) {
      return fetch(`${API_BASE}${path}`, { ...options, headers: authHeaders() });
    }
  }
  return res;
}

// ── Toast notifications ───────────────────────────────────────────────────────

function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  // Animate in
  requestAnimationFrame(() => toast.classList.add("toast-visible"));
  setTimeout(() => {
    toast.classList.remove("toast-visible");
    toast.addEventListener("transitionend", () => toast.remove());
  }, 4000);
}

// ── Status text ───────────────────────────────────────────────────────────────

function setStatus(text, isError = false) {
  statusText.textContent = text;
  statusText.className = isError ? "error" : "";
}

function clearStatus() {
  statusText.textContent = "PHI369 Labs · BrainC v1.0.0";
  statusText.className = "";
}

// ── Connection status poller (every 30s) ──────────────────────────────────────

async function pollHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(5000) });
    if (res.ok) {
      const data = await res.json();
      connDot.className = "conn-dot conn-ok";
      connLabel.textContent = "Connected";
      // Check readiness for queue depth
      try {
        const ready = await fetch(`${API_BASE}/health/ready`, { signal: AbortSignal.timeout(4000) });
        if (ready.ok) {
          const rd = await ready.json();
          const depth = rd.checks?.queue?.depth ?? 0;
          queueDepthEl.textContent = depth;
          queueDepthIndicator.style.display = depth > 0 ? "" : "none";
        }
      } catch (_) {}
    } else {
      setOffline();
    }
  } catch (_) {
    setOffline();
  }
}

function setOffline() {
  connDot.className = "conn-dot conn-offline";
  connLabel.textContent = "Offline";
}

pollHealth();
setInterval(pollHealth, 30000);

// ── Model switcher ────────────────────────────────────────────────────────────

async function loadModels() {
  try {
    const res = await apiFetch("/models");
    if (!res || !res.ok) return;
    const data = await res.json();
    const active = data.active || "braincbrain";
    modelNameDisplay.textContent = active;
    modelList.innerHTML = "";
    (data.models || []).forEach(m => {
      const item = document.createElement("button");
      item.className = "model-option" + (m === active ? " active" : "");
      item.textContent = m;
      item.onclick = () => switchModel(m);
      modelList.appendChild(item);
    });
    if (!data.models?.length) {
      modelList.innerHTML = `<div style="color:var(--muted);font-size:0.8rem;padding:0.5rem">No models found</div>`;
    }
  } catch (_) {}
}

async function switchModel(model) {
  if (!currentUser || currentUser.role !== "admin") {
    showToast("Only admins can switch models", "error");
    closeModelDropdown();
    return;
  }
  try {
    const res = await apiFetch("/models/switch", {
      method: "POST",
      body: JSON.stringify({ model }),
    });
    if (res && res.ok) {
      const data = await res.json();
      modelNameDisplay.textContent = data.new_model;
      showToast(`Switched to ${data.new_model}`, "success");
      await loadModels();
    } else if (res) {
      const d = await res.json();
      showToast(d.detail || "Switch failed", "error");
    }
  } catch (err) {
    showToast(`Switch failed: ${err.message}`, "error");
  }
  closeModelDropdown();
}

function closeModelDropdown() {
  modelDropdown.style.display = "none";
}

modelBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  const isOpen = modelDropdown.style.display !== "none";
  modelDropdown.style.display = isOpen ? "none" : "";
  if (!isOpen) loadModels();
});

document.addEventListener("click", (e) => {
  if (!document.getElementById("model-switcher").contains(e.target)) {
    closeModelDropdown();
  }
});

// ── Utilities ─────────────────────────────────────────────────────────────────

function generateId() {
  return crypto.randomUUID
    ? crypto.randomUUID()
    : Date.now().toString(36) + Math.random().toString(36).slice(2);
}

function formatRelativeTime(isoString) {
  const date = new Date(isoString);
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatMessageContent(text) {
  text = text.replace(/```(\w+)?\n?([\s\S]*?)```/g, (_, lang, code) =>
    `<pre><code>${escapeHtml(code.trim())}</code></pre>`
  );
  text = text.replace(/`([^`\n]+)`/g, (_, code) =>
    `<code>${escapeHtml(code)}</code>`
  );
  return text;
}

function scrollToBottom() {
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

function hideEmptyState() {
  if (emptyState) emptyState.style.display = "none";
}

// ── User display ──────────────────────────────────────────────────────────────

function updateUserDisplay() {
  if (!currentUser) return;
  userMenu.style.display = "";
  userDisplay.textContent = currentUser.display_name || currentUser.username;
  if (currentUser.role === "admin") adminLink.style.display = "";
}

async function logout() {
  if (refreshToken) {
    try {
      await apiFetch("/auth/logout", {
        method: "POST",
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch (_) {}
  }
  authToken = "";
  refreshToken = "";
  currentUser = null;
  redirectToLogin();
}

logoutBtn.addEventListener("click", logout);

// ── Tool activity panel ───────────────────────────────────────────────────────

function showToolActivity(toolName, toolResult) {
  toolPanel.style.display = "";
  toolPanelName.textContent = `⚡ tool: ${toolName}`;
  toolPanelResult.textContent = toolResult || "";
  toolsBadge.textContent = toolName;
  toolsBadge.style.display = "";
  toolPanelBody.style.display = "none";
  document.querySelector(".tool-panel-chevron").textContent = "▾";
}

function hideToolActivity() {
  toolPanel.style.display = "none";
  toolsBadge.style.display = "none";
}

toolPanelToggle.addEventListener("click", () => {
  const isOpen = toolPanelBody.style.display !== "none";
  toolPanelBody.style.display = isOpen ? "none" : "";
  document.querySelector(".tool-panel-chevron").textContent = isOpen ? "▾" : "▴";
});

// ── Message rendering ─────────────────────────────────────────────────────────

function appendMessage(role, content, id = null) {
  hideEmptyState();
  const group = document.createElement("div");
  group.className = "message-group";
  if (id) group.dataset.id = id;

  const roleEl = document.createElement("div");
  roleEl.className = `message-role ${role}`;
  roleEl.textContent = role === "user"
    ? (currentUser ? currentUser.display_name || "You" : "You")
    : "BrainC";

  const contentEl = document.createElement("div");
  contentEl.className = `message-content ${role}`;
  contentEl.innerHTML = formatMessageContent(escapeHtml(content));

  group.appendChild(roleEl);
  group.appendChild(contentEl);
  chatContainer.appendChild(group);
  scrollToBottom();
  return contentEl;
}

function appendStreamingMessage() {
  hideEmptyState();
  const group = document.createElement("div");
  group.className = "message-group";

  const roleEl = document.createElement("div");
  roleEl.className = "message-role assistant";
  roleEl.textContent = "BrainC";

  const contentEl = document.createElement("div");
  contentEl.className = "message-content assistant streaming-cursor";
  contentEl.textContent = "";

  group.appendChild(roleEl);
  group.appendChild(contentEl);
  chatContainer.appendChild(group);
  scrollToBottom();
  return contentEl;
}

// ── Sidebar — conversations ───────────────────────────────────────────────────

async function loadConversations() {
  try {
    const res = await apiFetch("/conversations");
    if (!res || !res.ok) return;
    const conversations = await res.json();
    renderConversationList(conversations);
  } catch (_) {}
}

function renderConversationList(conversations) {
  convList.innerHTML = "";
  if (!conversations.length) {
    const el = document.createElement("div");
    el.className = "sidebar-empty";
    el.textContent = "No conversations yet";
    convList.appendChild(el);
    return;
  }
  for (const conv of conversations) {
    const item = document.createElement("div");
    item.className = "conv-item" + (conv.id === currentConversationId ? " active" : "");
    item.dataset.id = conv.id;

    const titleEl = document.createElement("div");
    titleEl.className = "conv-title";
    titleEl.textContent = conv.title;

    const metaEl = document.createElement("div");
    metaEl.className = "conv-meta";

    const timeEl = document.createElement("span");
    timeEl.className = "conv-time";
    timeEl.textContent = formatRelativeTime(conv.updated_at);
    metaEl.appendChild(timeEl);

    if (conv.tags && conv.tags.length > 0) {
      for (const tag of conv.tags) {
        const tagEl = document.createElement("span");
        tagEl.className = "conv-tag";
        tagEl.textContent = tag;
        metaEl.appendChild(tagEl);
      }
    }

    item.appendChild(titleEl);
    item.appendChild(metaEl);
    item.addEventListener("click", () => switchConversation(conv.id));
    convList.appendChild(item);
  }
}

function switchConversation(id) {
  currentConversationId = id;
  [...convList.querySelectorAll(".conv-item")].forEach(el =>
    el.classList.toggle("active", el.dataset.id === id)
  );
  hideToolActivity();
  loadHistory();
}

// ── Sidebar — notes ───────────────────────────────────────────────────────────

async function loadNotes() {
  try {
    const res = await apiFetch("/tools/notes");
    if (!res || !res.ok) return;
    const data = await res.json();
    renderNotesList(data.notes || []);
  } catch (_) {}
}

function renderNotesList(notes) {
  notesList.innerHTML = "";
  if (!notes.length) {
    const el = document.createElement("div");
    el.className = "sidebar-empty";
    el.textContent = "No notes";
    notesList.appendChild(el);
    return;
  }
  for (const note of notes) {
    const item = document.createElement("div");
    item.className = "note-item";
    item.textContent = note.title;
    item.title = note.filename;
    notesList.appendChild(item);
  }
}

// ── Note modal ────────────────────────────────────────────────────────────────

function openNoteModal() {
  noteTitleInput.value = "";
  noteContentInput.value = "";
  noteModal.style.display = "";
  noteTitleInput.focus();
}

function closeNoteModal() {
  noteModal.style.display = "none";
}

async function createNote() {
  const title = noteTitleInput.value.trim();
  const content = noteContentInput.value.trim();
  if (!title) { noteTitleInput.focus(); return; }
  noteSaveBtn.disabled = true;
  try {
    const res = await apiFetch("/tools/notes", {
      method: "POST",
      body: JSON.stringify({ title, content }),
    });
    if (res && res.ok) {
      closeNoteModal();
      await loadNotes();
      showToast("Note saved", "success");
    } else if (res) {
      const err = await res.json();
      showToast(`Failed to save note: ${err.detail || res.status}`, "error");
    }
  } catch (err) {
    showToast(`Note save error: ${err.message}`, "error");
  } finally {
    noteSaveBtn.disabled = false;
  }
}

newNoteBtn.addEventListener("click", openNoteModal);
noteModalClose.addEventListener("click", closeNoteModal);
noteCancelBtn.addEventListener("click", closeNoteModal);
noteSaveBtn.addEventListener("click", createNote);
noteModal.addEventListener("click", (e) => { if (e.target === noteModal) closeNoteModal(); });

// ── History loading ───────────────────────────────────────────────────────────

async function loadHistory() {
  // Show skeleton while loading
  chatContainer.innerHTML = `<div class="skeleton-msg"></div><div class="skeleton-msg skeleton-msg-user"></div>`;

  try {
    const res = await apiFetch(
      `/history?conversation_id=${encodeURIComponent(currentConversationId)}`
    );
    if (!res || !res.ok) {
      showToast("Could not load history", "error");
      return;
    }
    const data = await res.json();
    chatContainer.innerHTML = "";
    chatContainer.appendChild(emptyState);
    emptyState.style.display = "";

    if (data.messages && data.messages.length > 0) {
      for (const msg of data.messages) {
        appendMessage(msg.role, msg.message, msg.id);
      }
    }
    clearStatus();
  } catch (err) {
    showToast(`Connection error: ${err.message}`, "error");
  }
}

// ── Sending messages ──────────────────────────────────────────────────────────

async function sendMessage(text) {
  if (!text.trim() || isStreaming) return;

  isStreaming = true;
  sendBtn.disabled = true;
  messageInput.disabled = true;
  hideToolActivity();
  appendMessage("user", text);
  const streamEl = appendStreamingMessage();
  let fullText = "";
  setStatus("BrainC is thinking...");

  try {
    const res = await apiFetch("/chat", {
      method: "POST",
      body: JSON.stringify({
        message: text,
        conversation_id: currentConversationId,
        tools_enabled: toolsToggle.checked,
      }),
    });

    if (!res || !res.ok) {
      const errText = res ? await res.text() : "No response";
      streamEl.classList.remove("streaming-cursor");

      if (res && res.status === 503) {
        streamEl.textContent = "BrainC is busy — please try again shortly.";
        showToast("BrainC is busy, please try again", "error");
      } else if (res && res.status === 429) {
        streamEl.textContent = "Too many requests — slow down.";
        showToast("Rate limit reached — please wait", "error");
      } else {
        streamEl.textContent = `[Error ${res ? res.status : "?"}] ${errText}`;
        showToast(`Error ${res ? res.status : "?"}`, "error");
      }
      setStatus("Error", true);
      return;
    }

    const toolUsed = res.headers.get("X-Tool-Used");
    const toolResult = res.headers.get("X-Tool-Result");
    if (toolUsed) showToolActivity(toolUsed, toolResult || "");

    const queuePos = res.headers.get("X-Queue-Position");
    if (queuePos && parseInt(queuePos) > 1) {
      setStatus(`Queued (position ${queuePos})...`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      fullText += chunk;
      streamEl.innerHTML = formatMessageContent(escapeHtml(fullText));
      scrollToBottom();
    }

    streamEl.classList.remove("streaming-cursor");
    clearStatus();
    await loadConversations();
  } catch (err) {
    streamEl.classList.remove("streaming-cursor");
    if (err.name === "AbortError") {
      streamEl.textContent = "[Request timed out]";
    } else {
      streamEl.textContent = `[Connection error] ${err.message}`;
      showToast("BrainC's brain is offline — is Ollama running?", "error");
    }
    setStatus("Failed to reach BrainC", true);
  } finally {
    isStreaming = false;
    sendBtn.disabled = false;
    messageInput.disabled = false;
    messageInput.focus();
  }
}

// ── Clear history ─────────────────────────────────────────────────────────────

async function clearHistory() {
  if (!confirm("Clear this conversation? This cannot be undone.")) return;
  try {
    const res = await apiFetch(
      `/history?conversation_id=${encodeURIComponent(currentConversationId)}`,
      { method: "DELETE" }
    );
    if (!res || !res.ok) { showToast("Failed to clear history", "error"); return; }
    chatContainer.innerHTML = "";
    chatContainer.appendChild(emptyState);
    emptyState.style.display = "";
    hideToolActivity();
    clearStatus();
    await loadConversations();
    showToast("Conversation cleared", "success");
  } catch (err) {
    showToast(`Clear failed: ${err.message}`, "error");
  }
}

// ── New chat ──────────────────────────────────────────────────────────────────

function newChat() {
  currentConversationId = generateId();
  chatContainer.innerHTML = "";
  chatContainer.appendChild(emptyState);
  emptyState.style.display = "";
  hideToolActivity();
  clearStatus();
  [...convList.querySelectorAll(".conv-item")].forEach(el => el.classList.remove("active"));
  messageInput.focus();
}

// ── Auto-resize textarea ──────────────────────────────────────────────────────

function autoResize() {
  messageInput.style.height = "auto";
  messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + "px";
}
messageInput.addEventListener("input", autoResize);

// ── Event listeners ───────────────────────────────────────────────────────────

inputForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = messageInput.value.trim();
  if (!text) return;
  messageInput.value = "";
  autoResize();
  sendMessage(text);
});

messageInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    inputForm.dispatchEvent(new Event("submit"));
  }
});

clearBtn.addEventListener("click", clearHistory);
newChatBtn.addEventListener("click", newChat);

// ── Keyboard shortcuts ────────────────────────────────────────────────────────

document.addEventListener("keydown", (e) => {
  // Ctrl+N — New chat
  if ((e.ctrlKey || e.metaKey) && e.key === "n") {
    e.preventDefault();
    newChat();
  }
  // Ctrl+K — Focus message input
  if ((e.ctrlKey || e.metaKey) && e.key === "k") {
    e.preventDefault();
    messageInput.focus();
    messageInput.select();
  }
  // Escape — close any open modal or dropdown
  if (e.key === "Escape") {
    closeNoteModal();
    closeModelDropdown();
  }
});

// ── Init ──────────────────────────────────────────────────────────────────────

(async function init() {
  if (!authToken) {
    redirectToLogin();
    return;
  }
  try {
    const res = await apiFetch("/auth/me");
    if (!res || !res.ok) {
      redirectToLogin();
      return;
    }
    currentUser = await res.json();
    updateUserDisplay();
  } catch (_) {
    redirectToLogin();
    return;
  }

  await Promise.all([loadHistory(), loadConversations(), loadNotes(), loadModels()]);
  messageInput.focus();
})();
