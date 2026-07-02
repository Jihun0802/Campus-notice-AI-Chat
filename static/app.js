const $ = (selector) => document.querySelector(selector);

const state = {
  loading: false,
  messages: [],
  notices: [],
  readNoticeIds: new Set(),
  savedNoticeIds: new Set(),
};

const STORAGE_KEYS = {
  read: "campusNoticeAi.readNoticeIds",
  saved: "campusNoticeAi.savedNoticeIds",
};

const recommendedQuestions = [
  { text: "졸업시험 신청 언제까지야?" },
  { text: "이번 주에 확인해야 할 학과 공지 정리해줘" },
  { text: "장학금 신청 공지 있어?" },
  { text: "컴퓨터네트워크 과제 관련 공지 찾아줘", context: { course_id: "computer-network" } },
  { text: "휴학 신청 기간 알려줘" },
];

function metaValue(value) {
  return value || "-";
}

function loadNoticeIdSet(key) {
  try {
    const raw = localStorage.getItem(key);
    const ids = raw ? JSON.parse(raw) : [];
    return new Set(Array.isArray(ids) ? ids.map(String) : []);
  } catch {
    return new Set();
  }
}

function saveNoticeIdSet(key, ids) {
  try {
    localStorage.setItem(key, JSON.stringify([...ids]));
  } catch {
    setStatus("브라우저 저장소를 사용할 수 없습니다.");
  }
}

function getNoticeId(notice) {
  return String(notice.id || notice.notice_id || notice.original_url || notice.title);
}

function noticeDetailUrl(notice) {
  return `/notice-detail.html?id=${encodeURIComponent(getNoticeId(notice))}`;
}

function isNoticeRead(notice) {
  return state.readNoticeIds.has(getNoticeId(notice));
}

function isNoticeSaved(notice) {
  return state.savedNoticeIds.has(getNoticeId(notice));
}

function getUserContext() {
  return {
    department: $("#department").value.trim(),
    grade: $("#grade").value,
    course_id: $("#courseId").value.trim(),
  };
}

function visibleForCurrentStudent(notice) {
  const context = getUserContext();
  const visibility = notice.visibility || "public";
  if (visibility === "public") return true;
  if (visibility === "department") {
    return !context.department || !notice.department || notice.department === context.department;
  }
  if (visibility === "grade") {
    return !context.grade || !notice.grade || notice.grade === context.grade;
  }
  if (visibility === "course") {
    return Boolean(context.course_id && notice.course_id === context.course_id);
  }
  return visibility !== "private";
}

function parseDate(value) {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function daysUntil(value) {
  const date = parseDate(value);
  if (!date) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.ceil((date.getTime() - today.getTime()) / 86400000);
}

function sortByPublishedDesc(notices) {
  return [...notices].sort((left, right) => {
    const leftDate = parseDate(left.published_at)?.getTime() || 0;
    const rightDate = parseDate(right.published_at)?.getTime() || 0;
    return rightDate - leftDate || getNoticeId(left).localeCompare(getNoticeId(right));
  });
}

function sortByDeadlineAsc(notices) {
  return [...notices].sort((left, right) => {
    const leftDays = daysUntil(left.deadline_at);
    const rightDays = daysUntil(right.deadline_at);
    return (leftDays ?? 9999) - (rightDays ?? 9999);
  });
}

function deadlineLabel(notice) {
  const days = daysUntil(notice.deadline_at);
  if (days === null) return "마감 없음";
  if (days < 0) return "마감 지남";
  if (days === 0) return "오늘 마감";
  return `${days}일 남음`;
}

function setStatus(text) {
  $("#statusText").textContent = text;
}

function renderStatus(counts) {
  setStatus(`공지 ${counts.notices}개, chunk ${counts.notice_chunks}개, 첨부 ${counts.notice_attachments || 0}개`);
}

function renderIngestionStatus(status) {
  const counts = status.counts || {};
  const attachments = status.attachments || {};
  const media = status.media || {};
  const embeddings = status.embeddings || {};
  const summary = status.summary || {};
  const ocrHealth = status.ocr_health || {};
  const sources = status.sources || [];
  const failureLogs = status.failure_logs || [];
  $("#ingestionStatus").innerHTML = `
    <div>
      <strong>${summary.total_notices ?? counts.notices ?? 0}</strong>
      <span>공지</span>
    </div>
    <div>
      <strong>${summary.total_chunks ?? counts.notice_chunks ?? 0}</strong>
      <span>청크</span>
    </div>
    <div>
      <strong>${summary.total_attachments ?? counts.notice_attachments ?? 0}</strong>
      <span>첨부</span>
    </div>
    <div>
      <strong>${summary.total_media ?? counts.notice_media ?? 0}</strong>
      <span>이미지</span>
    </div>
    <div>
      <strong>${summary.pdf_parse_success ?? attachments.parsed ?? 0}/${summary.pdf_attachments ?? attachments.pdf_total ?? 0}</strong>
      <span>PDF 파싱</span>
    </div>
    <div>
      <strong>${summary.image_ocr_success ?? media.parsed ?? 0}/${summary.image_media ?? media.image_total ?? 0}</strong>
      <span>OCR</span>
    </div>
    <div>
      <strong>${summary.total_embeddings ?? embeddings.embedded_chunks ?? 0}/${summary.total_chunks ?? embeddings.total_chunks ?? 0}</strong>
      <span>임베딩</span>
    </div>
    <div>
      <strong>${summary.failure_logs ?? failureLogs.length}</strong>
      <span>실패 로그</span>
    </div>
  `;
  $("#crawlStatusText").textContent = `마지막 수집: ${status.last_crawl_at || "-"}`;
  const detailTarget = $("#adminStatusDetails");
  if (!detailTarget) return;
  detailTarget.innerHTML = `
    <div class="admin-block">
      <h3>처리 상태</h3>
      <div class="admin-kv">
        <span>누락 임베딩</span><strong>${summary.missing_embeddings ?? embeddings.missing_embeddings ?? 0}</strong>
        <span>PDF 실패</span><strong>${summary.pdf_parse_failed ?? attachments.failed ?? 0}</strong>
        <span>OCR 실패/미지원</span><strong>${summary.image_ocr_failed ?? media.failed ?? 0}/${summary.image_ocr_unsupported ?? media.unsupported ?? 0}</strong>
        <span>OCR provider</span><strong>${ocrHealth.ocr_provider_available ? "사용 가능" : "미설정"}</strong>
      </div>
      <p class="status">${escapeHtml(ocrHealth.message || "OCR 상태 미확인")}</p>
    </div>
    <div class="admin-block">
      <h3>Source 상태</h3>
      <div class="admin-table">
        ${sources
          .map(
            (source) => `
              <div class="admin-row">
                <strong>${escapeHtml(source.name || source.source_id || "-")}</strong>
                <span>${source.enabled === false ? "disabled" : "enabled"}</span>
                <span>${source.notice_count || 0} notices</span>
                <span>${escapeHtml(source.last_crawl_at || "-")}</span>
                <span>${source.failure_count || 0} failures</span>
              </div>
            `
          )
          .join("") || '<div class="empty">등록된 source가 없습니다.</div>'}
      </div>
    </div>
    <div class="admin-block">
      <h3>최근 실패</h3>
      <div class="failure-list">
        ${failureLogs
          .slice(0, 5)
          .map(
            (log) => `
              <div class="failure-item">
                <strong>${escapeHtml(log.step)} · ${escapeHtml(log.target_type)}</strong>
                <span>${escapeHtml(log.created_at || "-")}</span>
                <p>${escapeHtml(log.error_message || log.message || "-")}</p>
              </div>
            `
          )
          .join("") || '<div class="empty">최근 실패 로그가 없습니다.</div>'}
      </div>
    </div>
  `;
}

async function api(path, options = {}) {
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

function renderRecommendedQuestions() {
  $("#recommendedQuestions").innerHTML = recommendedQuestions
    .map((question) => {
      const courseId = question.context?.course_id || "";
      return `<button class="quick-question" type="button" data-question="${escapeAttribute(question.text)}" data-course-id="${escapeAttribute(courseId)}">${escapeHtml(question.text)}</button>`;
    })
    .join("");
  document.querySelectorAll(".quick-question").forEach((button) => {
    button.addEventListener("click", () => {
      const question = button.dataset.question;
      if (button.dataset.courseId) {
        $("#courseId").value = button.dataset.courseId;
      }
      $("#chatInput").value = question;
      sendChatMessage(question).catch((error) => setStatus(`질문 실패: ${error.message}`));
    });
  });
}

function renderMetricCard(label, value, caption) {
  return `
    <div class="metric-card">
      <strong>${escapeHtml(value)}</strong>
      <span>${escapeHtml(label)}</span>
      <small>${escapeHtml(caption)}</small>
    </div>
  `;
}

function renderNoticeActions(notice) {
  const noticeId = getNoticeId(notice);
  const read = isNoticeRead(notice);
  const saved = isNoticeSaved(notice);
  return `
    <div class="notice-actions">
      <button class="notice-action" type="button" data-notice-action="read" data-notice-id="${escapeAttribute(noticeId)}">
        ${read ? "안읽음" : "읽음"}
      </button>
      <button class="notice-action ${saved ? "is-active" : ""}" type="button" data-notice-action="save" data-notice-id="${escapeAttribute(noticeId)}">
        ${saved ? "저장됨" : "저장"}
      </button>
      <a class="notice-action detail-action" href="${escapeAttribute(noticeDetailUrl(notice))}">상세</a>
    </div>
  `;
}

function renderFeedNotice(notice, compact = false) {
  const read = isNoticeRead(notice);
  const saved = isNoticeSaved(notice);
  const days = daysUntil(notice.deadline_at);
  const urgent = days !== null && days >= 0 && days <= 7;
  return `
    <article class="feed-item ${read ? "is-read" : "is-unread"} ${saved ? "is-saved" : ""}">
      <div class="feed-item-main">
        <div class="notice-title">
          <h3>${escapeHtml(notice.title)}</h3>
          <span class="status-pill ${urgent ? "urgent" : ""}">${escapeHtml(deadlineLabel(notice))}</span>
        </div>
        <div class="meta">
          <span>${escapeHtml(metaValue(notice.source_name))}</span>
          <span>${escapeHtml(metaValue(notice.category))}</span>
          <span>게시일 ${escapeHtml(metaValue(notice.published_at))}</span>
          ${notice.department ? `<span>${escapeHtml(notice.department)}</span>` : ""}
        </div>
        ${renderNoticeMediaPreview(notice)}
        ${compact ? "" : `<p class="snippet">${escapeHtml((notice.body_text || "").slice(0, 130))}</p>`}
      </div>
      ${renderNoticeActions(notice)}
    </article>
  `;
}

function renderFeedList(selector, notices, emptyText, compact = false) {
  const target = $(selector);
  if (!notices.length) {
    target.innerHTML = `<div class="empty">${escapeHtml(emptyText)}</div>`;
    return;
  }
  target.innerHTML = notices.map((notice) => renderFeedNotice(notice, compact)).join("");
}

function renderStudentHome(notices = state.notices) {
  state.notices = notices;
  const visible = notices.filter(visibleForCurrentStudent);
  const unread = visible.filter((notice) => !isNoticeRead(notice));
  const saved = sortByPublishedDesc(notices.filter(isNoticeSaved));
  const dueSoon = sortByDeadlineAsc(
    visible.filter((notice) => {
      const days = daysUntil(notice.deadline_at);
      return days !== null && days >= 0 && days <= 30;
    })
  );
  const personalized = sortByDeadlineAsc(unread.filter((notice) => notice.deadline_at)).concat(
    sortByPublishedDesc(unread.filter((notice) => !notice.deadline_at)),
    sortByPublishedDesc(visible.filter(isNoticeRead))
  );
  const newNotices = sortByPublishedDesc(unread);

  $("#homeMetrics").innerHTML = [
    renderMetricCard("맞춤 공지", String(visible.length), "현재 학생 조건 기준"),
    renderMetricCard("마감 임박", String(dueSoon.length), "30일 이내 마감"),
    renderMetricCard("새 공지", String(newNotices.length), "아직 읽지 않음"),
    renderMetricCard("저장한 공지", String(saved.length), "이 브라우저에 저장"),
  ].join("");

  $("#personalizedFeedCount").textContent = `${visible.length}개`;
  $("#deadlineFeedCount").textContent = `${dueSoon.length}개`;
  $("#newFeedCount").textContent = `${newNotices.length}개`;
  $("#savedFeedCount").textContent = `${saved.length}개`;
  $("#homeUpdatedAt").textContent = notices.length ? "DB 동기화 완료" : "DB 비어 있음";

  renderFeedList("#personalizedFeed", personalized.slice(0, 8), "학생 조건에 맞는 공지가 없습니다.");
  renderFeedList("#deadlineFeed", dueSoon.slice(0, 5), "마감 임박 공지가 없습니다.", true);
  renderFeedList("#newFeed", newNotices.slice(0, 5), "새 공지가 없습니다.", true);
  renderFeedList("#savedFeed", saved.slice(0, 5), "저장한 공지가 없습니다.", true);
}

function chunkTypeLabel(chunkType) {
  return (
    {
      body: "본문",
      pdf_text: "PDF",
      image_ocr: "이미지 OCR",
      image_summary: "이미지 요약",
    }[chunkType] || "근거"
  );
}

function renderNoticeMediaPreview(notice) {
  const media = Array.isArray(notice.media) ? notice.media.filter((item) => item.thumbnail_path || item.local_path || item.original_url) : [];
  if (!media.length) return "";
  return `
    <div class="notice-media-strip">
      ${media
        .slice(0, 3)
        .map((item) => {
          const thumb = item.thumbnail_path || item.local_path || item.original_url;
          const href = item.original_url || item.local_path || thumb;
          return `
            <a href="${escapeAttribute(href)}" target="_blank" rel="noreferrer">
              <img src="${escapeAttribute(thumb)}" alt="${escapeAttribute(item.alt_text || item.file_name || "공지 이미지")}" loading="lazy" />
            </a>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderSourceCard(source) {
  const attachmentMeta = source.attachment_file_name
    ? `<span>첨부 ${escapeHtml(source.attachment_file_name)}</span>`
    : "";
  const mediaUrl = source.media_original_url || source.media_local_path || "";
  const mediaThumb = source.media_thumbnail_path || source.media_local_path || source.media_original_url || "";
  const mediaPreview = mediaThumb
    ? `
      <a class="media-preview" href="${escapeAttribute(mediaUrl || mediaThumb)}" target="_blank" rel="noreferrer">
        <img src="${escapeAttribute(mediaThumb)}" alt="${escapeAttribute(source.media_alt_text || source.media_file_name || "공지 이미지")}" loading="lazy" />
      </a>
    `
    : "";
  const mediaMeta = source.media_file_name
    ? `<span>이미지 ${escapeHtml(source.media_file_name)}</span>`
    : "";
  return `
    <article class="source-card">
      <div class="source-card-header">
        <h3>${escapeHtml(source.title)}</h3>
        <span>${escapeHtml(chunkTypeLabel(source.chunk_type))}</span>
      </div>
      <div class="meta">
        <span>작성자 ${escapeHtml(metaValue(source.publisher))}</span>
        <span>학과 ${escapeHtml(metaValue(source.department))}</span>
        <span>게시일 ${escapeHtml(metaValue(source.published_at))}</span>
        <span>마감 ${escapeHtml(metaValue(source.deadline_at))}</span>
        <span>${escapeHtml(metaValue(source.category || source.visibility))}</span>
        ${attachmentMeta}
        ${mediaMeta}
      </div>
      ${mediaPreview}
      <p class="evidence">${escapeHtml(source.matched_text || "근거 문장이 없습니다.")}</p>
      <a class="source-link" href="${escapeAttribute(noticeDetailUrl(source))}">상세 보기</a>
      ${
        source.original_url
          ? `<a class="source-link attachment-link" href="${escapeAttribute(source.original_url)}" target="_blank" rel="noreferrer">원문 열기</a>`
          : ""
      }
      ${
        source.attachment_file_url
          ? `<a class="source-link attachment-link" href="${escapeAttribute(source.attachment_file_url)}" target="_blank" rel="noreferrer">첨부 열기</a>`
          : ""
      }
      ${
        mediaUrl
          ? `<a class="source-link attachment-link" href="${escapeAttribute(mediaUrl)}" target="_blank" rel="noreferrer">이미지 원본</a>`
          : ""
      }
    </article>
  `;
}

function renderChatMessage(message) {
  const sources = message.sources || [];
  const sourceHtml = sources.length
    ? `<div class="source-list">${sources.map(renderSourceCard).join("")}</div>`
    : '<div class="empty source-empty">표시할 출처가 없습니다.</div>';
  const meta = message.role === "assistant" && message.mode
    ? `<div class="message-meta">mode ${escapeHtml(message.mode)} · confidence ${escapeHtml(message.confidence || "-")}</div>`
    : "";

  return `
    <article class="chat-message ${message.role}">
      <div class="message-bubble">
        <p>${escapeHtml(message.content)}</p>
        ${meta}
      </div>
      ${message.role === "assistant" ? sourceHtml : ""}
    </article>
  `;
}

function renderChatMessages() {
  $("#chatMessages").innerHTML = state.messages.map(renderChatMessage).join("");
  $("#chatMessages").scrollTop = $("#chatMessages").scrollHeight;
}

async function sendChatMessage(question) {
  const query = (question || $("#chatInput").value).trim();
  if (!query || state.loading) return;

  state.loading = true;
  $("#chatInput").value = "";
  state.messages.push({ role: "user", content: query });
  renderChatMessages();
  setStatus("답변 생성 중...");

  try {
    const response = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        query,
        ...getUserContext(),
      }),
    });
    state.messages.push({
      role: "assistant",
      content: response.answer,
      mode: response.mode,
      confidence: response.confidence,
      sources: response.sources,
    });
    $("#chatMode").textContent = `${response.mode} · ${response.confidence}`;
    await refreshHealth();
  } catch (error) {
    state.messages.push({
      role: "assistant",
      content: `질문 처리에 실패했습니다: ${error.message}`,
      mode: "error",
      confidence: "low",
      sources: [],
    });
    setStatus(`질문 실패: ${error.message}`);
  } finally {
    state.loading = false;
    renderChatMessages();
  }
}

function renderRecent(notices) {
  $("#noticeCount").textContent = `${notices.length}개`;
  if (!notices.length) {
    $("#recentNotices").innerHTML = '<div class="empty">DB에 공지가 없습니다.</div>';
    return;
  }

  $("#recentNotices").innerHTML = notices
    .map(
      (notice) => `
        <article class="notice-item ${isNoticeRead(notice) ? "is-read" : "is-unread"}">
          <div class="notice-title">
            <h3>${escapeHtml(notice.title)}</h3>
            <span class="score">${notice.chunk_count || 0} chunks</span>
          </div>
          <div class="meta">
            <span>${escapeHtml(metaValue(notice.source_name))}</span>
            <span>게시일 ${escapeHtml(metaValue(notice.published_at))}</span>
            <span>${escapeHtml(metaValue(notice.category))}</span>
            <span>${escapeHtml(deadlineLabel(notice))}</span>
          </div>
          ${renderNoticeMediaPreview(notice)}
          ${renderNoticeActions(notice)}
        </article>
      `
    )
    .join("");
}

async function refreshHealth() {
  const data = await api("/api/health");
  renderStatus(data.counts);
}

async function refreshIngestionStatus() {
  const data = await api("/api/ingestion/status");
  renderIngestionStatus(data);
}

async function refreshRecent() {
  const data = await api("/api/notices?limit=50");
  state.notices = data.notices;
  renderStudentHome(state.notices);
  renderRecent(data.notices.slice(0, 8));
  await refreshHealth();
  await refreshIngestionStatus();
}

async function runAction(label, fn) {
  if (state.loading) return;
  state.loading = true;
  setStatus(`${label} 실행 중...`);
  try {
    const result = await fn();
    await refreshRecent();
    if (result?.embedding?.error) {
      setStatus(`${label} 완료, 임베딩 보류: ${result.embedding.error}`);
    } else {
      setStatus(`${label} 완료`);
    }
  } catch (error) {
    setStatus(`${label} 실패: ${error.message}`);
  } finally {
    state.loading = false;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

function refreshNoticeStateViews() {
  renderStudentHome(state.notices);
  renderRecent(state.notices.slice(0, 8));
}

function handleNoticeAction(action, noticeId) {
  if (!noticeId) return;
  if (action === "read") {
    if (state.readNoticeIds.has(noticeId)) {
      state.readNoticeIds.delete(noticeId);
    } else {
      state.readNoticeIds.add(noticeId);
    }
    saveNoticeIdSet(STORAGE_KEYS.read, state.readNoticeIds);
  }
  if (action === "save") {
    if (state.savedNoticeIds.has(noticeId)) {
      state.savedNoticeIds.delete(noticeId);
    } else {
      state.savedNoticeIds.add(noticeId);
    }
    saveNoticeIdSet(STORAGE_KEYS.saved, state.savedNoticeIds);
  }
  refreshNoticeStateViews();
}

function applyInitialQuestion() {
  const params = new URLSearchParams(window.location.search);
  const question = params.get("ask");
  if (!question) return;
  $("#chatInput").value = question;
  sendChatMessage(question).catch((error) => setStatus(`질문 실패: ${error.message}`));
}

state.readNoticeIds = loadNoticeIdSet(STORAGE_KEYS.read);
state.savedNoticeIds = loadNoticeIdSet(STORAGE_KEYS.saved);

document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : event.target?.parentElement;
  const button = target?.closest("[data-notice-action]");
  if (!button) return;
  handleNoticeAction(button.dataset.noticeAction, button.dataset.noticeId);
});

["#department", "#grade", "#courseId"].forEach((selector) => {
  const field = $(selector);
  field.addEventListener("change", () => renderStudentHome(state.notices));
  field.addEventListener("input", () => renderStudentHome(state.notices));
});

$("#chatForm").addEventListener("submit", (event) => {
  event.preventDefault();
  sendChatMessage().catch((error) => setStatus(`질문 실패: ${error.message}`));
});

$("#seedBtn").addEventListener("click", () =>
  runAction("샘플 공지", () =>
    api("/api/admin/seed", {
      method: "POST",
      body: JSON.stringify({ embed_after: true, embedding_batch_size: 32 }),
    })
  )
);

$("#crawlBtn").addEventListener("click", () =>
  runAction("공개 공지 수집", () =>
    api("/api/admin/crawl", {
      method: "POST",
      body: JSON.stringify({ limit: 3, embed_after: true, embedding_batch_size: 32 }),
    })
  )
);

$("#reindexBtn").addEventListener("click", () =>
  runAction("전체 재색인", () =>
    api("/api/admin/reindex", {
      method: "POST",
      body: JSON.stringify({ embed_after: true, embedding_batch_size: 32 }),
    })
  )
);

$("#embedBtn").addEventListener("click", () =>
  runAction("임베딩 생성", () =>
    api("/api/admin/embed", { method: "POST", body: JSON.stringify({ batch_size: 32 }) })
  )
);

renderRecommendedQuestions();
refreshRecent()
  .then(applyInitialQuestion)
  .catch((error) => setStatus(`초기화 실패: ${error.message}`));
