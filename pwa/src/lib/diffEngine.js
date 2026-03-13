/**
 * diffEngine.ts — Port of diff_engine.py
 *
 * LCS 기반 편집 거리 계산 및 문자 단위 diff 생성.
 * 내부 diff는 diff 패키지(Myers 알고리즘)를 사용한다.
 */
import { diffChars, diffLines } from 'diff';
// ---------------------------------------------------------------------------
// 편집 거리
// ---------------------------------------------------------------------------
/** 문자 단위 편집 거리 (insert + delete 수) */
function charEditDistance(a, b) {
    return diffChars(a, b).reduce((sum, c) => sum + (c.added || c.removed ? c.value.length : 0), 0);
}
/**
 * 줄 단위 diff로 범위를 좁힌 뒤 문자 단위 편집 거리를 계산한다.
 * 청크가 maxHunkSize를 초과하면 null(보수적 처리) 반환.
 */
export function efficientEditDistance(a, b, maxHunkSize = 10000) {
    const changes = diffLines(a, b);
    let total = 0;
    let i = 0;
    while (i < changes.length) {
        if (!changes[i].added && !changes[i].removed) {
            i++;
            continue;
        }
        // 연속된 changed 블록을 하나의 hunk로 모은다
        let aHunk = '';
        let bHunk = '';
        while (i < changes.length && (changes[i].added || changes[i].removed)) {
            if (changes[i].removed)
                aHunk += changes[i].value;
            else
                bHunk += changes[i].value;
            i++;
        }
        if (aHunk.length + bHunk.length > maxHunkSize)
            return null;
        total += charEditDistance(aHunk, bHunk);
    }
    return total;
}
/**
 * from → to 사이에서 삭제된 텍스트 hunk를 반환한다. (raw, 필터링 없음)
 * document.ts의 pruning 시 사용.
 */
export function computeDeletedHunks(from, to) {
    const diff = diffChars(from, to);
    const lines = from.split('\n');
    const hunks = [];
    let pos = 0;
    for (const chunk of diff) {
        if (chunk.removed) {
            const text = chunk.value;
            if (text.trim()) {
                let charCount = 0;
                let startLine = 0;
                let endLine = 0;
                const endPos = pos + text.length - 1;
                for (let l = 0; l < lines.length; l++) {
                    const lineEnd = charCount + lines[l].length;
                    if (startLine === 0 && pos <= lineEnd)
                        startLine = l;
                    if (endPos <= lineEnd) {
                        endLine = l;
                        break;
                    }
                    charCount += lines[l].length + 1;
                }
                let before = '';
                for (let l = startLine - 1; l >= 0; l--) {
                    if (lines[l].trim()) {
                        before = lines[l];
                        break;
                    }
                }
                let after = '';
                for (let l = endLine + 1; l < lines.length; l++) {
                    if (lines[l].trim()) {
                        after = lines[l];
                        break;
                    }
                }
                hunks.push({ before, deleted: text, after });
            }
            pos += text.length;
        }
        else if (!chunk.added) {
            pos += chunk.value.length;
        }
    }
    return hunks;
}
/**
 * 스냅샷 배열(오래된 순)을 순회하며 손실된 텍스트 hunk 목록을 반환한다.
 * - 현재 내용에 남아있는 텍스트는 제외
 * - 동일한 삭제 내용은 한 번만 포함 (dedup)
 */
export function getLostHunks(snapshots, currentContent) {
    if (snapshots.length < 2)
        return [];
    const seen = new Set();
    const hunks = [];
    for (let i = 0; i < snapshots.length - 1; i++) {
        for (const hunk of computeDeletedHunks(snapshots[i].content, snapshots[i + 1].content)) {
            const key = hunk.deleted.trim();
            if (key && !seen.has(key) && !currentContent.includes(key)) {
                seen.add(key);
                hunks.push(hunk);
            }
        }
    }
    return hunks;
}
// ---------------------------------------------------------------------------
// 화면 표시용 문자 단위 diff
// ---------------------------------------------------------------------------
/**
 * 화면 표시용 문자 단위 diff를 반환한다.
 * 반환값: [operation, text][] — operation은 'equal' | 'insert' | 'delete'
 */
export function getCharacterDiff(a, b) {
    return diffChars(a, b).map(c => {
        if (c.added)
            return ['insert', c.value];
        if (c.removed)
            return ['delete', c.value];
        return ['equal', c.value];
    });
}
