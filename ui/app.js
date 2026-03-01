/* BrainC UI — PHI369 Labs */

const API_BASE = "http://localhost:8000";

const chatContainer = document.getElementById("chat-container");
const emptyState = document.getElementById("empty-state");
const inputForm = document.getElementById("input-form");
const messageInput = document.getElementById("message-input");
const sendBtn = document.getElementById("send-btn");
const clearBtn = document.getElementById("clear-btn");
const statusBar = document.getElementById("status-bar");
const newChatBtn = document.getElementById("new-chat-btn");
const convList = document.getElementById("conv-list");

let isStreaming = false;
let currentConversationId = "default";

// ── Utilities ──────────────────────────────────────────────

function setStatus(text, isError = false) {
  statusBar.textContent = text;
  statusBar.className = isError ? "error" : "";
}

function clearStatus() {
  statusBar.textContent = "PHI369 Labs · BrainC v0.2.0 · offline-capable";
  statusBar.className = "";
}

function generateId() {
  return crypto.randomUUID
    ? crypto.randomUUID()
    : Date.now().toString(36) + Math.random().toString(36).slice(2);
}

function formatRelativeTime(isoString) {
  const date = new Date(isoString);
  const now = Date.now();
  const diff = now - date.getTime();
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
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatMessageContent(text) {
  // Simple code block rendering (``` ... ```)
  text = text.replace(/```(\w+)?\n?([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code>${escapeHtml(code.trim())}</code></pre>`;
  });
  // Inline code (`...`)
  text = text.replace(/`([^`\n]+)`/g, (_, code) => {
    return `<code>${escapeHtml(code)}</code>`;
  });
  // Escape remaining HTML in non-code content (already escaped above in code blocks)
  // Preserve line breaks
  return text;
}

function scrollToBottom() {
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

function hideEmptyState() {
  if (emptyState) emptyState.style.display = "none";
}

// ── Message rendering ──────────────────────────────────────

function appendMessage(role, content, id = null) {
  hideEmptyState();

  const group = document.createElement("div");
  group.className = "message-group";
  if (id) group.dataset.id = id;

  const roleEl = document.createElement("div");
  roleEl.className = `message-role ${role}`;
  roleEl.textContent = role === "user" ? "You" : "BrainC";

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

// ── Sidebar — conversation list ─────────────────────────────

async function loadConversations() {
  try {
    const res = await fetch(`${API_BASE}/conversations`);
    if (!res.ok) return;
    const conversations = await res.json();
    renderConversationList(conversations);
  } catch (_) {
    // Non-fatal; sidebar just stays empty
  }
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
  // Update active highlight without a full re-render
  [...convList.querySelectorAll(".conv-item")].forEach(el => {
    el.classList.toggle("active", el.dataset.id === id);
  });
  loadHistory();
}

// ── History loading ────────────────────────────────────────

async function loadHistory() {
  try {
    const res = await fetch(`${API_BASE}/history?conversation_id=${encodeURIComponent(currentConversationId)}`);
    if (!res.ok) {
      setStatus("Could not load history", true);
      return;
    }
    const data = await res.json();

    // Clear current messages (keep empty state hidden logic in appendMessage)
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
    setStatus(`Connection error: ${err.message}`, true);
  }
}

// ── Sending messages ───────────────────────────────────────

async function sendMessage(text) {
  if (!text.trim() || isStreaming) return;

  isStreaming = true;
  sendBtn.disabled = true;
  messageInput.disabled = true;

  appendMessage("user", text);

  const streamEl = appendStreamingMessage();
  let fullText = "";

  setStatus("BrainC is thinking...");

  try {
    const res = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: text,
        conversation_id: currentConversationId,
      }),
    });

    if (!res.ok) {
      const errText = await res.text();
      streamEl.classList.remove("streaming-cursor");
      streamEl.textContent = `[Error ${res.status}] ${errText}`;
      setStatus(`Error ${res.status}`, true);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      fullText += chunk;

      // Render raw text with basic formatting
      streamEl.innerHTML = formatMessageContent(escapeHtml(fullText));
      scrollToBottom();
    }

    streamEl.classList.remove("streaming-cursor");
    clearStatus();
    // Refresh sidebar so new conversation title appears
    await loadConversations();
  } catch (err) {
    streamEl.classList.remove("streaming-cursor");
    streamEl.textContent = `[Connection error] ${err.message}`;
    setStatus(`Failed to reach BrainC API at ${API_BASE}`, true);
  } finally {
    isStreaming = false;
    sendBtn.disabled = false;
    messageInput.disabled = false;
    messageInput.focus();
  }
}

// ── Clear history ──────────────────────────────────────────

async function clearHistory() {
  if (!confirm("Clear this conversation? This cannot be undone.")) return;

  try {
    const res = await fetch(
      `${API_BASE}/history?conversation_id=${encodeURIComponent(currentConversationId)}`,
      { method: "DELETE" }
    );
    if (!res.ok) {
      setStatus("Failed to clear history", true);
      return;
    }
    chatContainer.innerHTML = "";
    chatContainer.appendChild(emptyState);
    emptyState.style.display = "";
    clearStatus();
    await loadConversations();
  } catch (err) {
    setStatus(`Clear failed: ${err.message}`, true);
  }
}

// ── New chat ───────────────────────────────────────────────

function newChat() {
  currentConversationId = generateId();
  chatContainer.innerHTML = "";
  chatContainer.appendChild(emptyState);
  emptyState.style.display = "";
  clearStatus();
  // Deselect any active item; sidebar will refresh after first message
  [...convList.querySelectorAll(".conv-item")].forEach(el =>
    el.classList.remove("active")
  );
  messageInput.focus();
}

// ── Auto-resize textarea ───────────────────────────────────

function autoResize() {
  messageInput.style.height = "auto";
  messageInput.style.height = Math.min(messageInput.scrollHeight, 160) + "px";
}

messageInput.addEventListener("input", autoResize);

// ── Event listeners ────────────────────────────────────────

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

// ── Init ───────────────────────────────────────────────────

(async function init() {
  await Promise.all([loadHistory(), loadConversations()]);
  messageInput.focus();
})();
