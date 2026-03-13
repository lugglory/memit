/**
 * main.ts — Memit PWA 메인 UI
 *
 * 저장 전략:
 *   Ctrl+S            → IndexedDB에 커밋
 *   Ctrl+Shift+S / "파일에 저장" 버튼 → 실제 .memit 파일에 쓰기
 *   탭 닫기 전        → 저장되지 않은 파일 변경이 있으면 경고
 */

import './style.css';
import { MemitDocument } from './lib/document';
import { checkAmendSafe } from './lib/amendCheck';
import { getCharacterDiff, getLostHunks } from './lib/diffEngine';

// ---------------------------------------------------------------------------
// 상태
// ---------------------------------------------------------------------------

let doc: MemitDocument | null = null;
let lastSavedContent = '';
let modified = false;

// ---------------------------------------------------------------------------
// DOM 참조
// ---------------------------------------------------------------------------

function el<T extends HTMLElement>(id: string): T {
  const e = document.getElementById(id) as T | null;
  if (!e) throw new Error(`Element #${id} not found. Try a hard refresh (Ctrl+Shift+R).`);
  return e;
}

const statusBar   = el('status-bar');
const pageBar     = el('page-bar');
const editor      = el<HTMLTextAreaElement>('editor');
const saveBtn     = el<HTMLButtonElement>('save-btn');
const saveFileBtn = el<HTMLButtonElement>('save-file-btn');
const customMsgChk = el<HTMLInputElement>('custom-msg');
const exportBtn   = el<HTMLButtonElement>('export-btn');
const copyBtn     = el<HTMLButtonElement>('copy-btn');
const lostTextView = el<HTMLDivElement>('lost-text-view');

// ---------------------------------------------------------------------------
// 파일 열기 / 만들기
// ---------------------------------------------------------------------------

async function openFile() {
  const [handle] = await window.showOpenFilePicker({
    types: [{ description: 'Memit 파일', accept: { 'application/json': ['.memit'] } }],
  });
  doc = await MemitDocument.loadFromFile(handle);
  await doc.saveToDb();
  initApp();
}

async function newFile() {
  doc = MemitDocument.createNew();
  await doc.saveToDb();
  initApp();
}

// ---------------------------------------------------------------------------
// 앱 초기화 (문서 준비된 후)
// ---------------------------------------------------------------------------

function initApp() {
  if (!doc) return;
  document.getElementById('landing')!.style.display = 'none';
  document.getElementById('app')!.style.display = 'flex';
  document.title = `${doc.fileName} - Memit Memo`;
  loadCurrentPage();
}

function loadCurrentPage() {
  if (!doc) return;
  const content = doc.getContent();
  editor.value = content;
  lastSavedContent = content;
  _preChangeContent = content;
  modified = false;

  renderPageBar();
  renderLostView();
  updateStatus();
}

// ---------------------------------------------------------------------------
// 페이지 탭 렌더링
// ---------------------------------------------------------------------------

function renderPageBar() {
  if (!doc) return;
  pageBar.innerHTML = '';

  doc.getPages().forEach((page, idx) => {
    const tab = document.createElement('div');
    tab.className = 'page-tab' + (idx === doc!.getCurrentPageIdx() ? ' active' : '');
    tab.dataset.idx = String(idx);
    tab.textContent = page.title;
    tab.title = page.title;
    tab.addEventListener('click', () => switchPage(idx));
    tab.addEventListener('dblclick', e => { e.stopPropagation(); renamePage(page.id); });
    tab.addEventListener('contextmenu', e => showPageCtxMenu(e, idx));
    pageBar.appendChild(tab);
  });

  const addBtn = document.createElement('button');
  addBtn.className = 'page-add-btn';
  addBtn.textContent = '+';
  addBtn.title = '새 페이지 추가';
  addBtn.addEventListener('click', addPage);
  pageBar.appendChild(addBtn);
}

// ---------------------------------------------------------------------------
// 페이지 전환
// ---------------------------------------------------------------------------

function switchPage(idx: number) {
  if (!doc) return;
  doc.switchToPage(idx);
  loadCurrentPage();
}

// ---------------------------------------------------------------------------
// 페이지 추가
// ---------------------------------------------------------------------------

async function addPage() {
  if (!doc) return;
  const page = doc.addPage();
  doc.switchToPage(doc.getPages().length - 1);
  await doc.saveToDb();
  loadCurrentPage();
  flashStatus(`페이지 "${page.title}" 추가됨`);
}

// ---------------------------------------------------------------------------
// 페이지 이름 변경
// ---------------------------------------------------------------------------

async function renamePage(pageId: number) {
  if (!doc) return;
  const page = doc.getPages().find(p => p.id === pageId);
  if (!page) return;
  const newTitle = await promptDialog('페이지 제목을 입력하세요:', page.title);
  if (newTitle === null || !newTitle.trim()) return;
  doc.setPageTitle(pageId, newTitle.trim());
  await doc.saveToDb();
  renderPageBar();
  updateStatus();
  flashStatus(`페이지 이름 변경됨: "${newTitle.trim()}"`);
}

// ---------------------------------------------------------------------------
// 페이지 삭제
// ---------------------------------------------------------------------------

async function deletePage(idx: number) {
  if (!doc) return;
  const page = doc.getPages()[idx];
  if (!page) return;
  if (doc.getPages().length <= 1) {
    alert('마지막 페이지는 삭제할 수 없습니다.');
    return;
  }
  const ok = confirm(`"${page.title}" 페이지를 삭제할까요?\n스냅샷이 모두 사라집니다.`);
  if (!ok) return;
  doc.deletePage(page.id);
  await doc.saveToDb();
  loadCurrentPage();
  flashStatus(`페이지 삭제됨`);
}

// ---------------------------------------------------------------------------
// 페이지 컨텍스트 메뉴
// ---------------------------------------------------------------------------

let pageCtxIdx = -1;
const pageCtxMenu   = el<HTMLDivElement>('page-ctx-menu');
const pageCtxRename = el<HTMLDivElement>('page-ctx-rename');
const pageCtxDelete = el<HTMLDivElement>('page-ctx-delete');

function showPageCtxMenu(e: MouseEvent, idx: number) {
  e.preventDefault();
  pageCtxIdx = idx;
  pageCtxMenu.style.display = 'block';
  pageCtxMenu.style.left = `${e.clientX}px`;
  pageCtxMenu.style.top  = `${e.clientY}px`;
}

pageCtxRename.addEventListener('click', () => {
  hidePageCtxMenu();
  if (pageCtxIdx < 0 || !doc) return;
  const page = doc.getPages()[pageCtxIdx];
  if (page) renamePage(page.id);
});

pageCtxDelete.addEventListener('click', () => {
  hidePageCtxMenu();
  deletePage(pageCtxIdx);
});

function hidePageCtxMenu() { pageCtxMenu.style.display = 'none'; }

// ---------------------------------------------------------------------------
// 편집 감지 — 버퍼 + 트리거 기반 자동 커밋
// ---------------------------------------------------------------------------

const POST_DELETION_DELAY = 500;

let _preChangeContent = '';
let _inDeletionSeq    = false;
let _postDeletionTimer: ReturnType<typeof setTimeout> | null = null;

function schedulePostDeletionCommit() {
  if (_postDeletionTimer) clearTimeout(_postDeletionTimer);
  _postDeletionTimer = setTimeout(async () => {
    _postDeletionTimer = null;
    _inDeletionSeq = false;
    if (modified) await saveAndCommit(undefined, true);
  }, POST_DELETION_DELAY);
}

function cancelPostDeletionCommit() {
  if (_postDeletionTimer) { clearTimeout(_postDeletionTimer); _postDeletionTimer = null; }
}

editor.addEventListener('input', (e: Event) => {
  const current   = editor.value;
  const prev      = _preChangeContent;
  const inputType = (e as InputEvent).inputType ?? '';
  const composing = (e as InputEvent).isComposing ?? false;

  if (composing) {
    if (current !== lastSavedContent) { modified = true; updateStatus(); }
    return;
  }

  _preChangeContent = current;

  if (current !== lastSavedContent) { modified = true; updateStatus(); }

  const isDelete = inputType.startsWith('delete') || current.length < prev.length;

  if (isDelete) {
    if (!_inDeletionSeq) {
      _inDeletionSeq = true;
      if (prev !== lastSavedContent) saveAndCommit(prev, true);
    }
    schedulePostDeletionCommit();
  } else {
    if (!_inDeletionSeq) {
      cancelPostDeletionCommit();
    }
  }
});

// ---------------------------------------------------------------------------
// 키보드 단축키
// ---------------------------------------------------------------------------

document.addEventListener('keydown', e => {
  if (e.ctrlKey || e.metaKey) {
    const key = e.key.toLowerCase();
    if (key === 's' && e.shiftKey) { e.preventDefault(); saveToFile(); }
    else if (key === 's')          { e.preventDefault(); saveAndCommit(); }
  }
});

document.addEventListener('click',   () => hidePageCtxMenu());
document.addEventListener('keydown', e => { if (e.key === 'Escape') hidePageCtxMenu(); });

saveBtn.addEventListener('click',     () => saveAndCommit());
saveFileBtn.addEventListener('click', () => saveToFile());

// ---------------------------------------------------------------------------
// 커밋 → IndexedDB
// ---------------------------------------------------------------------------

async function saveAndCommit(contentOverride?: string, silent = false) {
  if (!doc) return;
  const newContent = contentOverride ?? editor.value;

  cancelPostDeletionCommit();

  let message: string;
  if (!silent && customMsgChk.checked) {
    const msg = await promptDialog('커밋 메시지를 입력하세요:', '');
    if (msg === null) return;
    message = msg.trim() || String(doc.getSnapshots().length + 1);
  } else {
    message = autoMessage(newContent);
  }

  try {
    const [success, resultMsg] = await doc.commit(newContent, message);
    if (success) {
      lastSavedContent = newContent;
      modified = (editor.value !== newContent);
      const prefix = resultMsg.includes('Amended') ? '✓ Amended' : '✓ Saved';
      if (!silent) flashStatus(`${prefix}: ${resultMsg}`);
    } else {
      if (!silent) flashStatus(`ℹ ${resultMsg}`);
    }
  } catch (e) {
    alert(`저장 실패: ${e}`);
    return;
  }
  renderLostView();
}

// ---------------------------------------------------------------------------
// 파일에 저장
// ---------------------------------------------------------------------------

async function saveToFile() {
  if (!doc) return;
  try {
    await doc.saveToFile();
    document.title = `${doc.fileName} - Memit Memo`;
    flashStatus(`파일에 저장됨: ${doc.fileName}`);
    updateStatus();
  } catch (e) {
    if ((e as Error).name !== 'AbortError') alert(`파일 저장 실패: ${e}`);
  }
}

// ---------------------------------------------------------------------------
// 탭/창 닫기 전 경고
// ---------------------------------------------------------------------------

window.addEventListener('beforeunload', e => {
  if (doc?.dirtyToFile) {
    e.preventDefault();
    e.returnValue = '파일에 저장되지 않은 변경사항이 있습니다. 닫으시겠습니까?';
  }
});

// ---------------------------------------------------------------------------
// 자동 커밋 메시지 생성
// ---------------------------------------------------------------------------

function autoMessage(newContent: string): string {
  if (!doc) return '';
  const snaps = doc.getSnapshots();
  let oldContent: string;

  if (snaps.length >= 2) {
    const secondLast = snaps.at(-2)!;
    const last       = snaps.at(-1)!;
    const { isSafe } = checkAmendSafe(
      { memo: secondLast.content },
      { memo: last.content },
      { memo: newContent },
    );
    oldContent = isSafe ? secondLast.content : last.content;
  } else {
    oldContent = doc.getContent();
  }

  const diff = getCharacterDiff(oldContent, newContent);
  let changed = '';
  for (const [op, text] of diff) {
    if (op === 'insert' || op === 'delete') {
      changed += text.replace(/\n/g, ' ');
      if (changed.length >= 10) break;
    }
  }
  changed = changed.trim();
  if (!changed) return '(no changes)';
  return changed.length > 10 ? changed.slice(0, 10) + '..' : changed;
}

// ---------------------------------------------------------------------------
// 클립보드 / TXT 내보내기
// ---------------------------------------------------------------------------

copyBtn.addEventListener('click', () => {
  navigator.clipboard.writeText(editor.value);
  flashStatus('클립보드에 복사됨');
});

exportBtn.addEventListener('click', async () => {
  if (!doc) return;
  try {
    await doc.exportTxt();
    flashStatus('TXT 저장됨');
  } catch (e) {
    if ((e as Error).name !== 'AbortError') alert(`저장 실패: ${e}`);
  }
});

// ---------------------------------------------------------------------------
// 손실 텍스트 뷰
// ---------------------------------------------------------------------------

function renderLostView() {
  if (!doc) return;
  lostTextView.innerHTML = '';

  const currentContent = doc.getContent();
  const accumulated    = doc.getAccumulatedLostHunks();
  const live           = getLostHunks(doc.getSnapshots(), currentContent);

  // 누적분(오래된 순) + live 합산, dedup + 현재 내용 필터
  const seen = new Set<string>();
  const hunks = [...accumulated, ...live].filter(h => {
    const key = h.deleted.trim();
    if (!key || seen.has(key) || currentContent.includes(key)) return false;
    seen.add(key);
    return true;
  });

  if (hunks.length === 0) {
    const empty = document.createElement('div');
    empty.className   = 'lost-empty';
    empty.textContent = '손실된 텍스트 없음';
    lostTextView.appendChild(empty);
    return;
  }

  for (const { before, deleted, after } of hunks) {
    const hunk = document.createElement('div');
    hunk.className = 'lost-hunk';

    if (before) {
      const bLine = document.createElement('div');
      bLine.className   = 'lost-ctx';
      bLine.textContent = before;
      hunk.appendChild(bLine);
    }

    const dLine = document.createElement('div');
    dLine.className   = 'lost-del';
    dLine.textContent = deleted;
    hunk.appendChild(dLine);

    if (after) {
      const aLine = document.createElement('div');
      aLine.className   = 'lost-ctx';
      aLine.textContent = after;
      hunk.appendChild(aLine);
    }

    lostTextView.appendChild(hunk);
  }
}

// ---------------------------------------------------------------------------
// 커스텀 다이얼로그
// ---------------------------------------------------------------------------

function promptDialog(label: string, initial: string): Promise<string | null> {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'dialog-overlay';

    const box = document.createElement('div');
    box.className = 'dialog-box';

    const p = document.createElement('p');
    p.textContent = label;

    const input = document.createElement('input');
    input.type  = 'text';
    input.value = initial;

    const actions = document.createElement('div');
    actions.className = 'dialog-actions';

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = '취소';
    const okBtn = document.createElement('button');
    okBtn.textContent = '확인';
    okBtn.style.background = '#1f538d';

    actions.appendChild(cancelBtn);
    actions.appendChild(okBtn);
    box.appendChild(p);
    box.appendChild(input);
    box.appendChild(actions);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    const finish = (value: string | null) => {
      document.body.removeChild(overlay);
      resolve(value);
    };

    setTimeout(() => { input.focus(); input.select(); }, 0);
    okBtn.addEventListener('click',     () => finish(input.value));
    cancelBtn.addEventListener('click', () => finish(null));
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter')  finish(input.value);
      if (e.key === 'Escape') finish(null);
    });
    overlay.addEventListener('click', e => { if (e.target === overlay) finish(null); });
  });
}

// ---------------------------------------------------------------------------
// 상태 표시
// ---------------------------------------------------------------------------

function updateStatus() {
  if (!doc) return;
  const snaps = doc.getSnapshots();
  const page  = doc.getCurrentPage();
  let status  = `[${page.title}] `;

  if (snaps.length > 0) {
    const last = snaps.at(-1)!;
    status += `Snapshot #${last.id}: ${last.message}`;
    status += modified ? ' | ✏️ 수정중' : ' | ✓';
  } else {
    status += modified ? '✏️ 수정중 (스냅샷 없음)' : 'No snapshots yet';
  }

  status += doc.dirtyToFile ? ' | 💾 파일 미저장' : ' | 📁 파일 저장됨';
  setStatus(`Status: ${status}`);
  saveFileBtn.style.borderColor = doc.dirtyToFile ? '#f0a500' : '';
}

function setStatus(text: string) { statusBar.textContent = text; }

let _flashTimer: ReturnType<typeof setTimeout> | null = null;
function flashStatus(text: string) {
  if (_flashTimer) clearTimeout(_flashTimer);
  setStatus(text);
  _flashTimer = setTimeout(() => { updateStatus(); _flashTimer = null; }, 2000);
}

// ---------------------------------------------------------------------------
// 드래그 패널 너비 조절
// ---------------------------------------------------------------------------

const dragHandle  = document.getElementById('drag-handle')!;
const editorPanel = document.getElementById('editor-panel')!;
const histPanel   = document.getElementById('history-panel')!;

dragHandle.addEventListener('mousedown', e => {
  e.preventDefault();
  const startX  = e.clientX;
  const startEW = editorPanel.getBoundingClientRect().width;
  const startHW = histPanel.getBoundingClientRect().width;
  const total   = startEW + startHW;

  const onMove = (ev: MouseEvent) => {
    const delta = ev.clientX - startX;
    const newEW = Math.max(200, Math.min(total - 200, startEW + delta));
    editorPanel.style.flex  = 'none';
    editorPanel.style.width = `${newEW}px`;
    histPanel.style.flex    = 'none';
    histPanel.style.width   = `${total - newEW}px`;
  };
  const onUp = () => {
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  };
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
});

// ---------------------------------------------------------------------------
// PWA 서비스 워커 등록
// ---------------------------------------------------------------------------

if ('serviceWorker' in navigator && import.meta.env.PROD) {
  navigator.serviceWorker.register('./sw.js');
}

// ---------------------------------------------------------------------------
// 랜딩: 세션 복원 시도 후 버튼 이벤트 등록
// ---------------------------------------------------------------------------

(async () => {
  const restored = await MemitDocument.restoreSession();
  if (restored) {
    doc = restored;
    initApp();
    return;
  }
  document.getElementById('landing')!.style.display = 'flex';
})();

document.getElementById('btn-open')!.addEventListener('click', async () => {
  try { await openFile(); }
  catch (e) { if ((e as Error).name !== 'AbortError') alert(`파일 열기 실패: ${e}`); }
});

document.getElementById('btn-new')!.addEventListener('click', async () => {
  try { await newFile(); }
  catch (e) { if ((e as Error).name !== 'AbortError') alert(`만들기 실패: ${e}`); }
});
