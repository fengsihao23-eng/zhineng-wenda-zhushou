/**
 * 生成请求/实例标识。
 *
 * 浏览器只在安全上下文（HTTPS 或 localhost）暴露 `crypto.randomUUID`，
 * 通过 http://<IP> 访问时会得到 undefined，导致写操作直接抛错。
 * `crypto.getRandomValues` 在非安全上下文同样可用，因此以它为基础，
 * 仅在完全缺少 crypto 时退回 Math.random。
 */
export function randomKey(): string {
  const bytes = new Uint8Array(16);
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    crypto.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  // 按 RFC 4122 设置版本位与变体位，保证格式与 UUID v4 一致。
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
