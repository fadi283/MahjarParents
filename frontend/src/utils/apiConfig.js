/**
 * Runtime-safe API base URL and media URL resolution for both same-origin
 * single-service hosting (Flask + built React dist) and split-origin PaaS
 * hosting (Vercel/Netlify frontend + Render/Railway Flask API).
 */

const LOCALHOST_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '[::1]']);

export function normalizeApiBaseUrl(rawUrl) {
  if (typeof rawUrl !== 'string') return '';
  const trimmed = rawUrl.trim();
  if (!trimmed || /[\s\u0000-\u001f]/.test(trimmed)) {
    return '';
  }

  let parsed;
  try {
    parsed = new URL(trimmed);
  } catch {
    return '';
  }

  const protocol = parsed.protocol.toLowerCase();
  const host = (parsed.hostname || '').toLowerCase();
  if (!host || parsed.username || parsed.password) {
    return '';
  }
  if (parsed.search || parsed.hash) {
    return '';
  }

  if (protocol === 'https:') {
    return `${protocol}//${parsed.host}`;
  }
  if (protocol === 'http:' && LOCALHOST_HOSTS.has(host)) {
    return `${protocol}//${parsed.host}`;
  }
  return '';
}

export function resolveApiBaseUrl(envOverride = null) {
  let raw = '';
  if (envOverride && typeof envOverride === 'object') {
    raw = envOverride.VITE_API_BASE_URL ?? '';
  } else {
    try {
      raw = import.meta.env?.VITE_API_BASE_URL ?? '';
    } catch {
      raw = '';
    }
    if (!raw && typeof process !== 'undefined' && process.env) {
      raw = process.env.VITE_API_BASE_URL ?? '';
    }
  }
  return normalizeApiBaseUrl(raw);
}

export const API_BASE_URL = resolveApiBaseUrl();

export function buildApiUrl(apiPath, baseUrl = API_BASE_URL) {
  const pathStr = typeof apiPath === 'string' ? apiPath.trim() : '';
  const normalizedPath = pathStr.startsWith('/') ? pathStr : `/${pathStr}`;
  const cleanBase = normalizeApiBaseUrl(baseUrl);
  return cleanBase ? `${cleanBase}${normalizedPath}` : normalizedPath;
}

export function resolveMediaUrl(rawUrl, baseUrl = API_BASE_URL) {
  if (typeof rawUrl !== 'string') return '';
  const trimmed = rawUrl.trim();
  if (!trimmed) return '';
  if (trimmed.startsWith('/api/media/')) {
    return buildApiUrl(trimmed, baseUrl);
  }
  return trimmed;
}
