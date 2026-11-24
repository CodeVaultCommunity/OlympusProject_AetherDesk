/** O store mantém apenas um asset recodificado por conta neste navegador. */
export type WallpaperRecord = { accountId: string; digest: string; image: Blob; thumbnail: Blob;
  width: number; height: number; updatedAt: number };
type StoredWallpaper = Omit<WallpaperRecord, 'image' | 'thumbnail'> & {
  imageBytes: ArrayBuffer; thumbnailBytes: ArrayBuffer; mime: string;
};

const MAX_SOURCE = 8 * 1024 * 1024;
const MAX_IMAGE = 2 * 1024 * 1024;
const MAX_EDGE = 4096;
const MAX_PIXELS = 16_000_000;

function imageType(bytes: Uint8Array): boolean {
  const png = bytes.length >= 8 && [137, 80, 78, 71, 13, 10, 26, 10].every((part, index) => bytes[index] === part);
  const jpeg = bytes.length >= 3 && bytes[0] === 255 && bytes[1] === 216 && bytes[2] === 255;
  const webp = bytes.length >= 12 && String.fromCharCode(...bytes.slice(0, 4)) === 'RIFF' &&
    String.fromCharCode(...bytes.slice(8, 12)) === 'WEBP';
  return png || jpeg || webp;
}

function canvasBlob(canvas: HTMLCanvasElement, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('WALLPAPER_ENCODE_FAILED')),
    'image/webp', quality));
}

function openStore(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('aetherdesk-wallpapers-v1', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('wallpapers', { keyPath: 'accountId' });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(new Error(`WALLPAPER_STORAGE_UNAVAILABLE:${request.error?.name}`));
  });
}

export async function loadWallpaper(accountId: string): Promise<WallpaperRecord | null> {
  const db = await openStore();
  try {
    return await new Promise((resolve, reject) => {
      const request = db.transaction('wallpapers', 'readonly').objectStore('wallpapers').get(accountId);
      request.onsuccess = () => {
        const row = request.result as StoredWallpaper | undefined;
        resolve(row ? { accountId: row.accountId, digest: row.digest, width: row.width,
          height: row.height, updatedAt: row.updatedAt,
          image: new Blob([row.imageBytes], { type: row.mime }),
          thumbnail: new Blob([row.thumbnailBytes], { type: row.mime }) } : null);
      };
      request.onerror = () => reject(new Error(`WALLPAPER_STORAGE_UNAVAILABLE:${request.error?.name}`));
    });
  } finally { db.close(); }
}

export async function removeWallpaper(accountId: string): Promise<void> {
  const db = await openStore();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = db.transaction('wallpapers', 'readwrite');
      transaction.objectStore('wallpapers').delete(accountId);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(new Error(`WALLPAPER_STORAGE_UNAVAILABLE:delete:${transaction.error?.name}`));
    });
  } finally { db.close(); }
}

export async function saveWallpaper(accountId: string, file: File): Promise<WallpaperRecord> {
  if (!file.size || file.size > MAX_SOURCE) throw new Error('WALLPAPER_TOO_LARGE');
  const header = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  if (!imageType(header)) throw new Error('WALLPAPER_INVALID_FORMAT');
  let bitmap: ImageBitmap;
  try { bitmap = await createImageBitmap(file); }
  catch { throw new Error('WALLPAPER_INVALID_IMAGE'); }
  try {
    if (!bitmap.width || !bitmap.height || bitmap.width > MAX_EDGE || bitmap.height > MAX_EDGE ||
      bitmap.width * bitmap.height > MAX_PIXELS) throw new Error('WALLPAPER_INVALID_DIMENSIONS');
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width; canvas.height = bitmap.height;
    const context = canvas.getContext('2d', { alpha: false });
    if (!context) throw new Error('WALLPAPER_ENCODE_FAILED');
    context.drawImage(bitmap, 0, 0);
    const image = await canvasBlob(canvas, .82);
    if (image.size > MAX_IMAGE) throw new Error('WALLPAPER_TOO_LARGE');
    const ratio = Math.min(320 / bitmap.width, 180 / bitmap.height, 1);
    canvas.width = Math.max(1, Math.round(bitmap.width * ratio));
    canvas.height = Math.max(1, Math.round(bitmap.height * ratio));
    canvas.getContext('2d', { alpha: false })!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const thumbnail = await canvasBlob(canvas, .65);
    const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', await image.arrayBuffer()))]
      .map(byte => byte.toString(16).padStart(2, '0')).join('');
    const existing = await loadWallpaper(accountId);
    if (existing?.digest === digest) return existing;
    const record = { accountId, digest, image, thumbnail, width: bitmap.width,
      height: bitmap.height, updatedAt: Date.now() };
    const stored: StoredWallpaper = { accountId, digest, width: bitmap.width, height: bitmap.height,
      updatedAt: record.updatedAt, imageBytes: await image.arrayBuffer(),
      thumbnailBytes: await thumbnail.arrayBuffer(), mime: image.type };
    const db = await openStore();
    try {
      await new Promise<void>((resolve, reject) => {
        const transaction = db.transaction('wallpapers', 'readwrite');
        const write = transaction.objectStore('wallpapers').put(stored);
        write.onerror = () => reject(new Error(`WALLPAPER_STORAGE_UNAVAILABLE:put:${write.error?.name}`));
        transaction.oncomplete = () => resolve();
        transaction.onerror = () => reject(new Error(`WALLPAPER_STORAGE_UNAVAILABLE:save:${transaction.error?.name}`));
      });
    } finally { db.close(); }
    return record;
  } finally { bitmap.close(); }
}
