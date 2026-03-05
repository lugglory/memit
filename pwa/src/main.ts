/**
 * main.ts — Memit PWA 메인 UI
 *
 * File System Access API로 .memit 파일을 열고,
 * 편집·저장·히스토리·diff를 모두 브라우저에서 처리한다.
 */

import './style.css';
import { MemitDocument, MemitSnapshot } from './lib/document';
import { checkAmendSafe } from './lib/amendCheck';
import { getCharacterDiff } from './lib/diffEngine';

// ---------------------------------------------------------------------------
// 상태
// ---------------------------------------------------------------------------

let doc: MemitDocument | null = null;
let snapshots: MemitSnapshot[] = [];   // 최신 순 (reversed)
let selectedRow = -1;
let lastSavedContent = '';
let modified = false;

// ---------------------------------------------------------------------------
// DOM 참조
// ---------------------------------------------------------------------------

const statusBar    = document.getElementById('status-bar')!;
const editor       = document.getElementById('editor') as HTMLTextAreaElement;
const saveBtn      = document.getElementById('save-btn') as HTMLButtonElement;
const customMsgChk = document.getElementById('custom-msg') as HTMLInputElement;
const exportBtn    = document.getElementById('export-btn') as HTMLButtonElement;
const copyBtn      = document.getElementById('copy-btn') as HTMLButtonElement;
const historyList  = document.getElementById('history-list') as HTMLUListElement;
const diffView     = document.getElementById('diff-view') as HTMLDivElement;
const restoreBtn   = document.getElementById('restore-btn') as HTMLButtonElement;
const ctxMenu      = document.getElementById('ctx-menu') as HTMLDivElement;
const ctxEdit      = document.getElementById('ctx-edit') as HTMLDivElement;

// ---------------------------------------------------------------------------
// 파일 열기 / 만들기
// ---------------------------------------------------------------------------

async function openFile() {
  const [handle] = await window.showOpenFilePicker({
    types: [{ description: 'Memit 파일', accept: { 'application/json': ['.memit'] } }],
  });
  doc = await MemitDocument.load(handle);
  initApp();
}

async function newFile() {
  const handle = await window.showSaveFilePicker({
    suggestedName: 'notes.memit',
    types: [{ description: 'Memit 파일', accept: { 'application/json': ['.memit'] } }],
  });
  doc = await MemitDocument.create(handle);
  initApp();
}

// ---------------------------------------------------------------------------
// 앱 초기화 (파일 열린 후)
// ---------------------------------------------------------------------------

function initApp() {
  if (!doc) return;
  document.getElementById('landing')!.style.display = 'none';
  document.getElementById('app')!.style.display = 'flex';
  document.title = `${doc.fileName} - Memit Memo`;

  const content = doc.getContent();
  editor.value = content;
  lastSavedContent = content;
  modified = false;

  refreshHistory();
  updateStatus();
}

// ---------------------------------------------------------------------------
// 편집 감지
// ---------------------------------------------------------------------------

editor.addEventListener('input', () => {
  if (editor.value !== lastSavedContent) {
    modified = true;
    updateStatus();
  }
});

// ---------------------------------------------------------------------------
// 저장 & 커밋
// ---------------------------------------------------------------------------

saveBtn.addEventListener('click', saveAndCommit);

document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault();
    saveAndCommit();
  }
});

async function saveAndCommit() {
  if (!doc) return;
  const newContent = editor.value;

  let message: string;
  if (customMsgChk.checked) {
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
      modified = false;
      const prefix = resultMsg.includes('Amended') ? '✓ Amended' : '✓ Saved';
      setStatus(`${prefix}: ${resultMsg}`);
      refreshHistory();
      updateStatus();
    } else {
      setStatus(`ℹ ${resultMsg}`);
    }
  } catch (e) {
    alert(`저장 실패: ${e}`);
  }
}

function autoMessage(newContent: string): string {
  if (!doc) return '';
  const snaps = doc.getSnapshots();
  let oldContent: string;

  if (snaps.length >= 2) {
    const secondLast = snaps.at(-2)!;
    const last = snaps.at(-1)!;
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
  setStatus('✓ 클립보드에 복사됨');
});

exportBtn.addEventListener('click', async () => {
  if (!doc) return;
  try {
    await doc.exportTxt();
    setStatus('✓ TXT 저장됨');
  } catch (e) {
    if ((e as Error).name !== 'AbortError') alert(`저장 실패: ${e}`);
  }
});

// ---------------------------------------------------------------------------
// 히스토리 패널
// ---------------------------------------------------------------------------

function refreshHistory() {
  if (!doc) return;
  historyList.innerHTML = '';
  snapshots = [...doc.getSnapshots()].reverse();
  selectedRow = -1;
  restoreBtn.disabled = true;
  diffView.innerHTML = '';

  if (snapshots.length === 0) {
    const li = document.createElement('li');
    li.textContent = 'No snapshots yet';
    li.style.color = '#666';
    historyList.appendChild(li);
    return;
  }

  snapshots.forEach((snap, i) => {
    const li = document.createElement('li');
    li.dataset.row = String(i);
    li.textContent = formatSnapEntry(snap);

    const changeType = getChangeType(snap, i);
    if (changeType === 'insert') li.style.background = '#1a3d1a';
    else if (changeType === 'delete') li.style.background = '#3d1a1a';
    else if (changeType === 'mixed')  li.style.background = '#1a2d3d';

    li.addEventListener('click', () => selectRow(i));
    li.addEventListener('contextmenu', e => showCtxMenu(e, i));
    historyList.appendChild(li);
  });
}

function formatSnapEntry(snap: MemitSnapshot): string {
  try {
    const dt = new Date(snap.timestamp);
    const ts = dt.toLocaleString('sv-SE').replace('T', ' ');
    return `#${snap.id}: ${snap.message} - ${ts}`;
  } catch {
    return `#${snap.id}: ${snap.message} - ${snap.timestamp}`;
  }
}

function getChangeType(snap: MemitSnapshot, index: number): 'insert' | 'delete' | 'mixed' {
  if (index >= snapshots.length - 1) return 'insert';
  const prev = snapshots[index + 1];
  if (!prev.content && snap.content) return 'insert';
  if (prev.content && !snap.content) return 'delete';
  try {
    const diff = getCharacterDiff(prev.content, snap.content);
    const hasIns = diff.some(([op]) => op === 'insert');
    const hasDel = diff.some(([op]) => op === 'delete');
    if (hasIns && hasDel) return 'mixed';
    return hasIns ? 'insert' : (hasDel ? 'delete' : 'mixed');
  } catch {
    return 'mixed';
  }
}

function selectRow(row: number) {
  // 이전 선택 해제
  historyList.querySelectorAll('li.selected').forEach(el => el.classList.remove('selected'));

  selectedRow = row;
  const li = historyList.querySelector<HTMLLIElement>(`li[data-row="${row}"]`);
  li?.classList.add('selected');
  restoreBtn.disabled = false;

  const snap = snapshots[row];
  const oldContent = row + 1 < snapshots.length ? snapshots[row + 1].content : '';
  showDiff(oldContent, snap.content);
}

// ---------------------------------------------------------------------------
// Diff 표시
// ---------------------------------------------------------------------------

function showDiff(oldContent: string, newContent: string) {
  diffView.innerHTML = '';
  if (oldContent === newContent) {
    diffView.textContent = '[No differences - content is identical]';
    return;
  }
  try {
    for (const [op, text] of getCharacterDiff(oldContent, newContent)) {
      const span = document.createElement('span');
      span.textContent = text;
      if (op === 'insert') span.className = 'diff-ins';
      else if (op === 'delete') span.className = 'diff-del';
      diffView.appendChild(span);
    }
  } catch (e) {
    diffView.textContent = `Error generating diff: ${e}`;
  }
}

// ---------------------------------------------------------------------------
// 버전 복원
// ---------------------------------------------------------------------------

restoreBtn.addEventListener('click', async () => {
  if (selectedRow < 0 || selectedRow >= snapshots.length) return;
  const snap = snapshots[selectedRow];
  const ok = confirm(
    `Snapshot #${snap.id}을 복원할까요?\n\n` +
    `메시지: ${snap.message}\n시간: ${snap.timestamp}\n\n` +
    '현재 저장되지 않은 내용은 사라집니다.'
  );
  if (!ok) return;
  editor.value = snap.content;
  lastSavedContent = '';
  modified = true;
  updateStatus();
  alert(`Snapshot #${snap.id}이 에디터에 복원되었습니다.\n저장하려면 Save & Commit 버튼을 누르세요.`);
});

// ---------------------------------------------------------------------------
// 컨텍스트 메뉴 (우클릭 → 커밋 메시지 수정)
// ---------------------------------------------------------------------------

let ctxRow = -1;

function showCtxMenu(e: MouseEvent, row: number) {
  e.preventDefault();
  ctxRow = row;
  ctxMenu.style.display = 'block';
  ctxMenu.style.left = `${e.clientX}px`;
  ctxMenu.style.top  = `${e.clientY}px`;
}

ctxEdit.addEventListener('click', async () => {
  hideCtxMenu();
  if (ctxRow < 0 || ctxRow >= snapshots.length || !doc) return;
  const snap = snapshots[ctxRow];
  const newMsg = await promptDialog(
    `Snapshot #${snap.id}의 메시지를 수정:`,
    snap.message
  );
  if (newMsg === null || !newMsg.trim() || newMsg.trim() === snap.message) return;
  await doc.updateMessage(snap.id, newMsg.trim());
  setStatus(`✓ Snapshot #${snap.id} 메시지 수정됨`);
  refreshHistory();
});

document.addEventListener('click', () => hideCtxMenu());
document.addEventListener('keydown', e => { if (e.key === 'Escape') hideCtxMenu(); });

function hideCtxMenu() { ctxMenu.style.display = 'none'; }

// ---------------------------------------------------------------------------
// 커스텀 다이얼로그 (prompt 대체 — IME 안전)
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
    input.type = 'text';
    input.value = initial;

    const actions = document.createElement('div');
    actions.className = 'dialog-actions';

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = '취소';
    const okBtn = document.createElement('button');
    okBtn.textContent = '확인';
    okBtn.style.background = 'var(--accent)';

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

    okBtn.addEventListener('click', () => finish(input.value));
    cancelBtn.addEventListener('click', () => finish(null));
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') finish(input.value);
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
  let status: string;
  if (snaps.length > 0) {
    const last = snaps.at(-1)!;
    status = `Snapshot #${last.id}: ${last.message}`;
    status += modified ? ' | Modified ✏️' : ' | Clean ✓';
  } else {
    status = 'No snapshots yet';
    if (modified) status += ' | Modified ✏️';
  }
  setStatus(`Status: ${status}`);
}

function setStatus(text: string) { statusBar.textContent = text; }

// ---------------------------------------------------------------------------
// 드래그로 패널 너비 조절
// ---------------------------------------------------------------------------

const dragHandle  = document.getElementById('drag-handle')!;
const editorPanel = document.getElementById('editor-panel')!;
const histPanel   = document.getElementById('history-panel')!;

dragHandle.addEventListener('mousedown', e => {
  e.preventDefault();
  const startX = e.clientX;
  const startEW = editorPanel.getBoundingClientRect().width;
  const startHW = histPanel.getBoundingClientRect().width;
  const total   = startEW + startHW;

  const onMove = (ev: MouseEvent) => {
    const delta = ev.clientX - startX;
    const newEW = Math.max(200, Math.min(total - 200, startEW + delta));
    editorPanel.style.flex = 'none';
    editorPanel.style.width = `${newEW}px`;
    histPanel.style.flex = 'none';
    histPanel.style.width = `${total - newEW}px`;
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

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('./sw.js');
}

// ---------------------------------------------------------------------------
// 랜딩 버튼 바인딩
// ---------------------------------------------------------------------------

document.getElementById('btn-open')!.addEventListener('click', async () => {
  try { await openFile(); }
  catch (e) { if ((e as Error).name !== 'AbortError') alert(`파일 열기 실패: ${e}`); }
});

document.getElementById('btn-new')!.addEventListener('click', async () => {
  try { await newFile(); }
  catch (e) { if ((e as Error).name !== 'AbortError') alert(`파일 만들기 실패: ${e}`); }
});

