/**
 * storage.ts — IndexedDB 래퍼
 *
 * 저장 레코드 구조: { handle: FileSystemFileHandle | null, data: SerializedDoc }
 */

const DB_NAME = 'memit';
const STORE   = 'docs';

let _db: IDBDatabase | null = null;

function openDb(): Promise<IDBDatabase> {
  if (_db) return Promise.resolve(_db);
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => { _db = req.result; resolve(_db); };
    req.onerror   = () => reject(req.error);
  });
}

interface DbRecord {
  handle: FileSystemFileHandle | null;
  data: unknown;
}

export async function idbSave(
  key: string,
  handle: FileSystemFileHandle | null,
  data: unknown
): Promise<void> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readwrite');
    tx.objectStore(STORE).put({ handle, data } satisfies DbRecord, key);
    tx.oncomplete = () => resolve();
    tx.onerror    = () => reject(tx.error);
  });
}

export async function idbLoad(
  key: string
): Promise<{ handle: FileSystemFileHandle | null; data: unknown } | null> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, 'readonly');
    const req = tx.objectStore(STORE).get(key);
    req.onsuccess = () => resolve(req.result as DbRecord ?? null);
    req.onerror   = () => reject(req.error);
  });
}
