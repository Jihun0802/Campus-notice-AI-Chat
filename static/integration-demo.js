const widgetState = {
  messages: [],
  loading: false,
};

function widgetEscapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function widgetEscapeAttribute(value) {
  return widgetEscapeHtml(value).replaceAll("`", "&#096;");
}

async function widgetApi(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

function renderWidgetSourceCard(source) {
  return `
    <article class="source-card">
      <div class="source-card-header">
        <h3>${widgetEscapeHtml(source.title)}</h3>
        <span>${widgetEscapeHtml(source.category || source.visibility || "-")}</span>
      </div>
      <div class="meta">
        <span>작성자 ${widgetEscapeHtml(source.publisher || "-")}</span>
        <span>게시일 ${widgetEscapeHtml(source.published_at || "-")}</span>
        <span>마감 ${widgetEscapeHtml(source.deadline_at || "-")}</span>
      </div>
      <p class="evidence">${widgetEscapeHtml(source.matched_text || "근거 문장이 없습니다.")}</p>
      ${
        source.original_url
          ? `<a class="source-link" href="${widgetEscapeAttribute(source.original_url)}" target="_blank" rel="noreferrer">원문 열기</a>`
          : ""
      }
    </article>
  `;
}

function renderWidgetMessage(message) {
  const sources = message.sources || [];
  return `
    <article class="chat-message ${message.role}">
      <div class="message-bubble">
        <p>${widgetEscapeHtml(message.content)}</p>
        ${
          message.mode
            ? `<div class="message-meta">mode ${widgetEscapeHtml(message.mode)} · confidence ${widgetEscapeHtml(message.confidence || "-")}</div>`
            : ""
        }
      </div>
      ${message.role === "assistant" ? `<div class="source-list">${sources.map(renderWidgetSourceCard).join("")}</div>` : ""}
    </article>
  `;
}

function renderWidgetMessages() {
  const root = document.querySelector("#widgetMessages");
  root.innerHTML = widgetState.messages.map(renderWidgetMessage).join("");
  root.scrollTop = root.scrollHeight;
}

async function sendWidgetMessage(question) {
  if (!question || widgetState.loading) return;
  widgetState.loading = true;
  widgetState.messages.push({ role: "user", content: question });
  renderWidgetMessages();

  try {
    const response = await widgetApi("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        query: question,
        department: "모바일시스템공학과",
        grade: "4",
      }),
    });
    widgetState.messages.push({
      role: "assistant",
      content: response.answer,
      mode: response.mode,
      confidence: response.confidence,
      sources: response.sources,
    });
  } catch (error) {
    widgetState.messages.push({
      role: "assistant",
      content: `질문 처리에 실패했습니다: ${error.message}`,
      mode: "error",
      confidence: "low",
      sources: [],
    });
  } finally {
    widgetState.loading = false;
    renderWidgetMessages();
  }
}

document.querySelector("#floatingChatButton").addEventListener("click", () => {
  document.querySelector("#floatingChatPanel").classList.toggle("is-open");
  if (!widgetState.messages.length) {
    sendWidgetMessage("장학금 신청 공지 있어?");
  }
});

document.querySelector("#floatingCloseButton").addEventListener("click", () => {
  document.querySelector("#floatingChatPanel").classList.remove("is-open");
});

document.querySelector("#widgetForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const input = document.querySelector("#widgetInput");
  const question = input.value.trim();
  input.value = "";
  sendWidgetMessage(question);
});
