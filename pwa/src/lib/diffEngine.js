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
