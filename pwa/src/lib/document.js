/**
 * document.ts — Memit 멀티 페이지 문서
 *
 * .memit 포맷 v2: 여러 페이지를 하나의 파일에 담는다.
 * v1 파일을 열면 자동으로 단일 페이지로 마이그레이션한다.
 *
 * 저장 전략:
 *   commit() / 페이지 조작 → IndexedDB(__active__)에만 저장
 *   saveToFile()           → 실제 파일에 쓰기 (handle 없으면 피커 열림)
 */
import { checkAmendSafe } from './amendCheck';
import { idbSave, idbLoad } from './storage';
const IDB_KEY = '__active__';
// ---------------------------------------------------------------------------
// MemitDocument
// ---------------------------------------------------------------------------
export class MemitDocument {
    handle = null;
    get fileName() {
        return this.handle?.name ?? '(저장 안 됨)';
    }
    pages = [];
    currentPageIdx = 0;
    nextPageId = 1;
    /** IndexedDB 내용이 실제 파일과 다를 때 true */
    dirtyToFile = false;
    constructor() { }
    // ------------------------------------------------------------------
    // 페이지 관리
    // ------------------------------------------------------------------
    getCurrentPage() {
        return this.pages[this.currentPageIdx];
    }
    getPages() {
        return this.pages;
    }
    getCurrentPageIdx() {
        return this.currentPageIdx;
    }
    switchToPage(idx) {
        if (idx >= 0 && idx < this.pages.length) {
            this.currentPageIdx = idx;
        }
    }
    addPage(title) {
        const page = {
            id: this.nextPageId++,
            title: title ?? `Page ${this.pages.length + 1}`,
            nextId: 1,
            snapshots: [],
        };
        this.pages.push(page);
        return page;
    }
    /** 페이지를 삭제한다. 마지막 페이지는 삭제 불가. */
    deletePage(pageId) {
        if (this.pages.length <= 1)
            return false;
        const idx = this.pages.findIndex(p => p.id === pageId);
        if (idx === -1)
            return false;
        this.pages.splice(idx, 1);
        if (this.currentPageIdx >= this.pages.length) {
            this.currentPageIdx = this.pages.length - 1;
        }
        return true;
    }
    setPageTitle(pageId, title) {
        const page = this.pages.find(p => p.id === pageId);
        if (page)
            page.title = title;
    }
    // ------------------------------------------------------------------
    // 현재 페이지 콘텐츠 / 스냅샷
    // ------------------------------------------------------------------
    getContent() {
        return this.getCurrentPage().snapshots.at(-1)?.content ?? '';
    }
    getSnapshots() {
        return this.getCurrentPage().snapshots;
    }
    // ------------------------------------------------------------------
    // 직렬화 / 역직렬화
    // ------------------------------------------------------------------
    serialize() {
        return {
            format_version: 2,
            next_page_id: this.nextPageId,
            pages: this.pages.map(p => ({
                id: p.id,
                title: p.title,
                next_id: p.nextId,
                snapshots: p.snapshots.map(s => ({
                    id: s.id,
                    message: s.message,
                    timestamp: s.timestamp,
                    content: s.content,
                    parent: s.parent,
                    amended: s.amended,
                    amend_count: s.amendCount,
                })),
            })),
        };
    }
    static _parsePages(raw) {
        if (raw.format_version === 1) {
            const v1 = raw;
            return {
                nextPageId: 2,
                pages: [{
                        id: 1,
                        title: 'Page 1',
                        nextId: v1.next_id ?? 1,
                        snapshots: (v1.snapshots ?? []).map(s => ({
                            id: s.id,
                            message: s.message,
                            timestamp: s.timestamp,
                            content: s.content,
                            parent: s.parent ?? null,
                            amended: s.amended ?? false,
                            amendCount: s.amend_count ?? 0,
                        })),
                    }],
            };
        }
        const v2 = raw;
        return {
            nextPageId: v2.next_page_id ?? 1,
            pages: (v2.pages ?? []).map(p => ({
                id: p.id,
                title: p.title,
                nextId: p.next_id ?? 1,
                snapshots: (p.snapshots ?? []).map(s => ({
                    id: s.id,
                    message: s.message,
                    timestamp: s.timestamp,
                    content: s.content,
                    parent: s.parent ?? null,
                    amended: s.amended ?? false,
                    amendCount: s.amend_count ?? 0,
                })),
            })),
        };
    }
    // ------------------------------------------------------------------
    // 팩토리
    // ------------------------------------------------------------------
    /** 빈 문서 생성 (파일 없음) */
    static createNew() {
        const doc = new MemitDocument();
        doc.addPage('Page 1');
        return doc;
    }
    /** 파일에서 불러오기 */
    static async loadFromFile(handle) {
        const file = await handle.getFile();
        const raw = JSON.parse(await file.text());
        const doc = new MemitDocument();
        doc.handle = handle;
        const { pages, nextPageId } = MemitDocument._parsePages(raw);
        doc.pages = pages;
        doc.nextPageId = nextPageId;
        if (doc.pages.length === 0)
            doc.addPage('Page 1');
        doc.dirtyToFile = false;
        return doc;
    }
    /** IndexedDB 레코드에서 복원 */
    static fromRecord(handle, data) {
        const doc = new MemitDocument();
        doc.handle = handle;
        const { pages, nextPageId } = MemitDocument._parsePages(data);
        doc.pages = pages;
        doc.nextPageId = nextPageId;
        if (doc.pages.length === 0)
            doc.addPage('Page 1');
        return doc;
    }
    /** IndexedDB에 저장된 마지막 세션을 복원. 없으면 null. */
    static async restoreSession() {
        const rec = await idbLoad(IDB_KEY);
        if (!rec)
            return null;
        return MemitDocument.fromRecord(rec.handle, rec.data);
    }
    // ------------------------------------------------------------------
    // 저장
    // ------------------------------------------------------------------
    async saveToDb() {
        await idbSave(IDB_KEY, this.handle, this.serialize());
        this.dirtyToFile = true;
    }
    /**
     * 실제 파일에 저장.
     * - handle이 있으면 덮어쓰기
     * - handle이 없으면 SaveFilePicker 열기 → handle 획득 후 저장
     */
    async saveToFile() {
        if (!this.handle) {
            this.handle = await window.showSaveFilePicker({
                suggestedName: 'notes.memit',
                types: [{ description: 'Memit 파일', accept: { 'application/json': ['.memit'] } }],
            });
        }
        const writable = await this.handle.createWritable();
        await writable.write(JSON.stringify(this.serialize(), null, 2));
        await writable.close();
        // handle 정보를 IDB에도 갱신
        await idbSave(IDB_KEY, this.handle, this.serialize());
        this.dirtyToFile = false;
    }
    // ------------------------------------------------------------------
    // 커밋 (현재 페이지)
    // ------------------------------------------------------------------
    async commit(content, message) {
        const page = this.getCurrentPage();
        const snaps = page.snapshots;
        const last = snaps.at(-1) ?? null;
        const secondLast = snaps.length >= 2 ? snaps.at(-2) : null;
        const makeSnap = (c, m, parent) => ({
            id: page.nextId++,
            message: m,
            timestamp: new Date().toISOString(),
            content: c,
            parent,
            amended: false,
            amendCount: 0,
        });
        if (!last) {
            snaps.push(makeSnap(content, message, null));
            await this.saveToDb();
            return [true, `Created snapshot ${snaps.at(-1).id}`];
        }
        if (content === last.content) {
            return [false, 'nothing to commit, content unchanged'];
        }
        if (!secondLast) {
            snaps.push(makeSnap(content, message, last.id));
            await this.saveToDb();
            return [true, `Created snapshot ${snaps.at(-1).id}`];
        }
        const { isSafe, reason } = checkAmendSafe({ memo: secondLast.content }, { memo: last.content }, { memo: content });
        if (isSafe) {
            last.content = content;
            last.message = message;
            last.timestamp = new Date().toISOString();
            last.amended = true;
            last.amendCount++;
            await this.saveToDb();
            return [true, `Amended snapshot ${last.id} (${reason})`];
        }
        else {
            snaps.push(makeSnap(content, message, last.id));
            await this.saveToDb();
            return [true, `Created snapshot ${snaps.at(-1).id} (amend unsafe: ${reason})`];
        }
    }
    async updateMessage(snapId, message) {
        const snap = this.getCurrentPage().snapshots.find(s => s.id === snapId);
        if (snap) {
            snap.message = message;
            await this.saveToDb();
        }
    }
    // ------------------------------------------------------------------
    // TXT 내보내기 (현재 페이지)
    // ------------------------------------------------------------------
    async exportTxt() {
        const baseName = (this.handle?.name ?? 'notes').replace(/\.memit$/, '');
        const pageTitle = this.getCurrentPage().title;
        const handle = await window.showSaveFilePicker({
            suggestedName: `${baseName}_${pageTitle}.txt`,
            types: [{ description: '텍스트 파일', accept: { 'text/plain': ['.txt'] } }],
        });
        const writable = await handle.createWritable();
        await writable.write(this.getContent());
        await writable.close();
    }
}
