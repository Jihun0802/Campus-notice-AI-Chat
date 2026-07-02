const $ = (selector) => document.querySelector(selector);

const STORAGE_KEYS = {
  read: "campusNoticeAi.readNoticeIds",
  saved: "campusNoticeAi.savedNoticeIds",
};

let currentNotice = null;
let readNoticeIds = loadNoticeIdSet(STORAGE_KEYS.read);
let savedNoticeIds = loadNoticeIdSet(STORAGE_KEYS.saved);

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
    renderError("브라우저 저장소를 사용할 수 없습니다.");
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

function metaValue(value) {
  return value || "-";
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

function getNoticeId(notice) {
  return String(notice.id || notice.notice_id || notice.original_url || notice.title);
}

async function api(path) {
  const response = await fetch(path);
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

function renderActions() {
  if (!currentNotice) return;
  const noticeId = getNoticeId(currentNotice);
  const read = readNoticeIds.has(noticeId);
  const saved = savedNoticeIds.has(noticeId);
  $("#detailActions").innerHTML = `
    <button class="notice-action" type="button" data-detail-action="read">
      ${read ? "안읽음" : "읽음"}
    </button>
    <button class="notice-action ${saved ? "is-active" : ""}" type="button" data-detail-action="save">
      ${saved ? "저장됨" : "저장"}
    </button>
  `;
}

function renderAttachment(attachment) {
  const preview = attachment.extracted_text_preview
    ? `<p class="snippet">${escapeHtml(attachment.extracted_text_preview)}</p>`
    : '<p class="snippet muted">추출된 텍스트가 없습니다.</p>';
  return `
    <article class="detail-list-item">
      <div class="notice-title">
        <h3>${escapeHtml(attachment.file_name)}</h3>
        <span class="score">${escapeHtml(attachment.file_type || "file")}</span>
      </div>
      <div class="meta">
        <span>다운로드 ${escapeHtml(metaValue(attachment.download_status))}</span>
        <span>파싱 ${escapeHtml(metaValue(attachment.parse_status))}</span>
        ${attachment.error_message ? `<span>오류 ${escapeHtml(attachment.error_message)}</span>` : ""}
      </div>
      ${preview}
      ${attachment.file_url ? `<a class="source-link" href="${escapeAttribute(attachment.file_url)}" target="_blank" rel="noreferrer">첨부 열기</a>` : ""}
    </article>
  `;
}

function renderMediaItem(media) {
  const imageUrl = media.thumbnail_path || media.local_path || media.original_url;
  const originalUrl = media.original_url || media.local_path || imageUrl;
  const preview = media.ocr_text_preview
    ? `<p class="snippet">${escapeHtml(media.ocr_text_preview)}</p>`
    : '<p class="snippet muted">OCR 텍스트가 없습니다.</p>';
  return `
    <article class="detail-media-item">
      ${
        imageUrl
          ? `<a href="${escapeAttribute(originalUrl)}" target="_blank" rel="noreferrer"><img src="${escapeAttribute(imageUrl)}" alt="${escapeAttribute(media.alt_text || media.file_name || "공지 이미지")}" loading="lazy" /></a>`
          : ""
      }
      <h3>${escapeHtml(media.file_name)}</h3>
      <div class="meta">
        <span>${escapeHtml(media.file_type || "image")}</span>
        <span>저장 ${escapeHtml(metaValue(media.download_status))}</span>
        <span>OCR ${escapeHtml(metaValue(media.parse_status))}</span>
      </div>
      ${preview}
      ${media.error_message ? `<p class="snippet muted">${escapeHtml(media.error_message)}</p>` : ""}
    </article>
  `;
}

function renderDetail(notice) {
  currentNotice = notice;
  const noticeId = getNoticeId(notice);
  $("#detailTitle").textContent = notice.title;
  $("#detailMeta").textContent = [
    notice.source_name,
    notice.publisher,
    notice.department,
    notice.category,
    notice.published_at ? `게시일 ${notice.published_at}` : "",
    notice.deadline_at ? `마감 ${notice.deadline_at}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
  $("#detailBody").innerHTML = escapeHtml(notice.body_text || "본문이 없습니다.").replaceAll("\n", "<br />");
  if (notice.original_url) {
    $("#originalLink").href = notice.original_url;
    $("#originalLink").hidden = false;
  } else {
    $("#originalLink").hidden = true;
  }

  const attachments = Array.isArray(notice.attachments) ? notice.attachments : [];
  const media = Array.isArray(notice.media) ? notice.media : [];
  $("#attachmentCount").textContent = `${attachments.length}개`;
  $("#mediaCount").textContent = `${media.length}개`;
  $("#attachmentList").innerHTML = attachments.length
    ? attachments.map(renderAttachment).join("")
    : '<div class="empty">첨부파일이 없습니다.</div>';
  $("#mediaGallery").innerHTML = media.length
    ? media.map(renderMediaItem).join("")
    : '<div class="empty">이미지가 없습니다.</div>';

  const chunkSummary = notice.chunks || {};
  const byType = Array.isArray(chunkSummary.by_type) ? chunkSummary.by_type : [];
  $("#chunkSummary").innerHTML = `
    <div>
      <strong>${chunkSummary.total_chunks || 0}</strong>
      <span>전체 청크</span>
    </div>
    <div>
      <strong>${chunkSummary.embedded_chunks || 0}</strong>
      <span>임베딩 완료</span>
    </div>
    ${byType
      .map(
        (item) => `
          <div>
            <strong>${item.count || 0}</strong>
            <span>${escapeHtml(chunkTypeLabel(item.chunk_type))}</span>
          </div>
        `
      )
      .join("")}
  `;
  $("#processingSummary").innerHTML = `
    <span>첨부 PDF</span><strong>${attachments.filter((item) => item.file_type === "pdf").length}</strong>
    <span>PDF 파싱 실패</span><strong>${attachments.filter((item) => item.parse_status === "failed").length}</strong>
    <span>이미지 OCR 성공</span><strong>${media.filter((item) => item.parse_status === "parsed").length}</strong>
    <span>이미지 OCR 실패/미지원</span><strong>${media.filter((item) => ["failed", "unsupported"].includes(item.parse_status)).length}</strong>
  `;
  $("#askChatLink").href = `/?ask=${encodeURIComponent(notice.title)}&notice_id=${encodeURIComponent(noticeId)}`;
  renderActions();
}

function renderError(message) {
  $("#detailTitle").textContent = "공지 상세를 불러오지 못했습니다.";
  $("#detailMeta").textContent = message;
  $("#detailBody").innerHTML = `<div class="empty">${escapeHtml(message)}</div>`;
}

function handleDetailAction(action) {
  if (!currentNotice) return;
  const noticeId = getNoticeId(currentNotice);
  if (action === "read") {
    if (readNoticeIds.has(noticeId)) {
      readNoticeIds.delete(noticeId);
    } else {
      readNoticeIds.add(noticeId);
    }
    saveNoticeIdSet(STORAGE_KEYS.read, readNoticeIds);
  }
  if (action === "save") {
    if (savedNoticeIds.has(noticeId)) {
      savedNoticeIds.delete(noticeId);
    } else {
      savedNoticeIds.add(noticeId);
    }
    saveNoticeIdSet(STORAGE_KEYS.saved, savedNoticeIds);
  }
  renderActions();
}

document.addEventListener("click", (event) => {
  const target = event.target instanceof Element ? event.target : event.target?.parentElement;
  const button = target?.closest("[data-detail-action]");
  if (!button) return;
  handleDetailAction(button.dataset.detailAction);
});

async function init() {
  const params = new URLSearchParams(window.location.search);
  const id = params.get("id");
  if (!id) {
    renderError("공지 id가 없습니다.");
    return;
  }
  const data = await api(`/api/notice?id=${encodeURIComponent(id)}`);
  renderDetail(data.notice);
}

init().catch((error) => renderError(error.message));
