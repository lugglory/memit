/**
 * amendCheck.ts — Port of amend_check.py
 *
 * 삼각 부등식을 이용해 amend가 안전한지 판단한다.
 * d(A,B) + d(B,C) == d(A,C) 이면 B는 A→C 최단 경로 위에 있으므로 안전.
 */

import { efficientEditDistance } from './diffEngine';

type FileMap = Record<string, string | null>;

export interface AmendResult {
  isSafe: boolean;
  reason: string;
}

export function checkAmendSafe(
  aFiles: FileMap,
  bFiles: FileMap,
  cFiles: FileMap
): AmendResult {
  const allKeys = new Set([
    ...Object.keys(aFiles),
    ...Object.keys(bFiles),
    ...Object.keys(cFiles),
  ]);

  for (const key of allKeys) {
    const a = aFiles[key] ?? '';
    const b = bFiles[key] ?? '';
    const c = cFiles[key] ?? '';

    // null = 바이너리 파일 취급: 변경이 있으면 보수적으로 거부
    if (aFiles[key] === null || bFiles[key] === null || cFiles[key] === null) {
      if (a !== b || b !== c) {
        return { isSafe: false, reason: `Binary file changed: ${key}` };
      }
      continue;
    }

    if (a === b && b === c) continue;

    const dAB = efficientEditDistance(a, b);
    const dBC = efficientEditDistance(b, c);
    const dAC = efficientEditDistance(a, c);

    if (dAB === null || dBC === null || dAC === null) {
      return { isSafe: false, reason: `File too large for diff: ${key}` };
    }

    if (dAB + dBC !== dAC) {
      return {
        isSafe: false,
        reason: `Information loss in ${key}: d(A,B)=${dAB} + d(B,C)=${dBC} != d(A,C)=${dAC}`,
      };
    }
  }

  return { isSafe: true, reason: 'All changes are on the shortest edit path' };
}
