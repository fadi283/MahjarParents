export const WHATSAPP_SHARE_BASE_URL = 'https://wa.me/';
export const FACEBOOK_SHARE_BASE_URL =
  'https://www.facebook.com/sharer/sharer.php';
export const DEFAULT_SHARE_TITLE =
  'إعلان من لجنة أولياء أمور مدرسة المحجر الابتدائية';
export const DEFAULT_FORM_SHARE_TITLE =
  'نموذج تفاعل – لجنة أولياء أمور مدرسة المحجر الابتدائية';
export const POST_HASH_PREFIX = 'post-';
export const FORM_HASH_PREFIX = 'form-';

const BIDI_OVERRIDE_RE = /[\u202a-\u202e\u2066-\u2069]/g;
const CONTROL_CHARS_RE = /[\x00-\x1f\x7f]/g;
const CONTROL_CHARS_NO_NL_RE = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g;
const DANGEROUS_BLOCK_RE =
  /<\s*(script|style|iframe|object|embed|svg)\b[^>]*>[\s\S]*?<\s*\/\s*\1\s*>/gi;
const HTML_TAG_RE = /<\s*\/?[a-zA-Z!][^<>]*>/g;
const UNCLOSED_TAG_RE = /<\s*\/?[a-zA-Z!][^\s<>]*/g;
const DANGEROUS_SCHEME_RE = /(?:javascript|vbscript|data\s*:\s*text\/html)\s*:/gi;
const UNSAFE_URL_CHARS_RE = /[\s\x00-\x1f\x7f<>"']/;

/**
 * Sanitize plain text for sharing across WhatsApp, Facebook, Telegram, Email, and Web Share API.
 */
export function sanitizeShareText(value, { allowNewlines = false } = {}) {
  if (typeof value !== 'string') return '';

  let cleaned = value
    .replace(/\r\n/g, allowNewlines ? '\n' : ' ')
    .replace(/\r/g, allowNewlines ? '\n' : ' ')
    .replace(BIDI_OVERRIDE_RE, '')
    .replace(allowNewlines ? CONTROL_CHARS_NO_NL_RE : CONTROL_CHARS_RE, ' ');

  for (let i = 0; i < 5; i += 1) {
    const previous = cleaned;
    cleaned = cleaned.replace(DANGEROUS_BLOCK_RE, ' ');
    cleaned = cleaned.replace(HTML_TAG_RE, ' ');
    if (cleaned === previous) break;
  }

  cleaned = cleaned.replace(UNCLOSED_TAG_RE, ' ');
  cleaned = cleaned.replace(DANGEROUS_SCHEME_RE, '');
  cleaned = cleaned.replace(/[<>]/g, ' ');

  if (allowNewlines) {
    cleaned = cleaned
      .split('\n')
      .map((line) => line.replace(/[ \t]+/g, ' ').trim())
      .join('\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
    return cleaned.slice(0, 1000).trim();
  }

  cleaned = cleaned.replace(/\s+/g, ' ').trim();
  return cleaned.slice(0, 200).trim();
}

/**
 * Validate and normalize an HTTP/HTTPS URL without embedded credentials or unsafe chars.
 */
export function sanitizeHttpUrl(rawUrl) {
  if (typeof rawUrl !== 'string') return null;
  const candidate = rawUrl.trim();
  if (!candidate || UNSAFE_URL_CHARS_RE.test(candidate)) {
    return null;
  }

  let parsed;
  try {
    parsed = new URL(candidate);
  } catch {
    return null;
  }

  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    return null;
  }
  if (parsed.username || parsed.password) {
    return null;
  }

  return parsed.toString();
}

function sanitizeShareTargetUrl(rawUrl) {
  const safeHttp = sanitizeHttpUrl(rawUrl);
  if (safeHttp) return safeHttp;

  if (typeof rawUrl !== 'string') return null;
  const candidate = rawUrl.trim();
  if (
    !candidate ||
    UNSAFE_URL_CHARS_RE.test(candidate) ||
    !candidate.startsWith('/') ||
    candidate.startsWith('//')
  ) {
    return null;
  }

  return candidate;
}

function normalizeBaseUrl(rawBase) {
  const safeBase = sanitizeHttpUrl(rawBase);
  if (!safeBase) return null;

  const parsed = new URL(safeBase);
  let pathname = parsed.pathname || '/';
  if (pathname === '/admin' || pathname === '/admin/') {
    pathname = '/';
  }
  if (!pathname.startsWith('/')) {
    pathname = `/${pathname}`;
  }

  return `${parsed.origin}${pathname}`;
}

function normalizeEntityId(rawId) {
  if (typeof rawId === 'number' && Number.isFinite(rawId)) {
    return String(rawId);
  }
  if (typeof rawId === 'string') {
    const trimmed = rawId.trim();
    if (trimmed) return trimmed;
  }
  return null;
}

function resolveNormalizedBase({ baseUrl, location } = {}) {
  const resolvedLocation =
    location ?? (typeof window !== 'undefined' ? window.location : null);

  return (
    normalizeBaseUrl(baseUrl) ??
    normalizeBaseUrl(resolvedLocation?.href) ??
    '/'
  );
}

/**
 * Construct a direct deep link to a specific announcement/event post.
 */
export function buildPostDeepLink(post, { baseUrl, location } = {}) {
  const explicitUrl =
    post && typeof post === 'object' && !Array.isArray(post)
      ? post.directUrl ?? post.direct_url ?? post.shareUrl ?? post.share_url
      : null;

  const safeExplicit = sanitizeHttpUrl(explicitUrl);
  if (safeExplicit) {
    return safeExplicit;
  }

  const normalizedBase = resolveNormalizedBase({ baseUrl, location });
  const postId =
    post && typeof post === 'object' && !Array.isArray(post)
      ? normalizeEntityId(post.id)
      : null;

  const hash = postId
    ? `#${POST_HASH_PREFIX}${encodeURIComponent(postId)}`
    : '#announcements-feed';

  return `${normalizedBase}${hash}`;
}

/**
 * Construct a platform deep link (#form-<id>) to an interactive engagement form.
 * Always targets the platform page rather than the raw external Google Form URL.
 */
export function buildFormDeepLink(form, { baseUrl, location } = {}) {
  const normalizedBase = resolveNormalizedBase({ baseUrl, location });
  const formId =
    form && typeof form === 'object' && !Array.isArray(form)
      ? normalizeEntityId(form.id)
      : null;

  const hash = formId
    ? `#${FORM_HASH_PREFIX}${encodeURIComponent(formId)}`
    : '#engagement-section';

  return `${normalizedBase}${hash}`;
}

/**
 * Construct a direct deep link for either a post or an engagement form.
 */
export function buildEntityDeepLink(
  entity,
  { entityType = 'post', baseUrl, location } = {}
) {
  if (entityType === 'form') {
    return buildFormDeepLink(entity, { baseUrl, location });
  }
  return buildPostDeepLink(entity, { baseUrl, location });
}

function parseEntityIdFromLocation(locationOrHash, hashPrefix, queryKey) {
  if (!locationOrHash) return null;

  let hash = '';
  let search = '';

  if (typeof locationOrHash === 'string') {
    const trimmed = locationOrHash.trim();
    if (!trimmed) return null;

    if (trimmed.startsWith('#')) {
      hash = trimmed;
    } else if (trimmed.startsWith('?')) {
      search = trimmed;
    } else {
      try {
        const parsed = new URL(trimmed);
        hash = parsed.hash || '';
        search = parsed.search || '';
      } catch {
        const hashIdx = trimmed.indexOf('#');
        if (hashIdx !== -1) {
          hash = trimmed.slice(hashIdx);
        }
      }
    }
  } else if (typeof locationOrHash === 'object') {
    hash = typeof locationOrHash.hash === 'string' ? locationOrHash.hash : '';
    search =
      typeof locationOrHash.search === 'string' ? locationOrHash.search : '';
  } else {
    return null;
  }

  const prefix = `#${hashPrefix}`;
  if (hash.startsWith(prefix)) {
    const rawId = hash.slice(prefix.length);
    if (!rawId) return null;
    try {
      const decoded = decodeURIComponent(rawId).trim();
      return decoded || null;
    } catch {
      return null;
    }
  }

  if (search) {
    try {
      const params = new URLSearchParams(search);
      const fromQuery = params.get(queryKey);
      if (fromQuery && fromQuery.trim()) {
        return fromQuery.trim();
      }
    } catch {
      return null;
    }
  }

  return null;
}

/**
 * Extract a post ID from a browser Location object, URL string, or hash string.
 */
export function parsePostIdFromLocation(locationOrHash) {
  return parseEntityIdFromLocation(locationOrHash, POST_HASH_PREFIX, 'post');
}

/**
 * Extract an engagement form ID from a browser Location object, URL string, or hash string.
 */
export function parseFormIdFromLocation(locationOrHash) {
  return parseEntityIdFromLocation(locationOrHash, FORM_HASH_PREFIX, 'form');
}

/**
 * Build a Facebook sharer URL for a validated target URL.
 */
export function buildFacebookShareUrl(url) {
  const safeUrl = sanitizeShareTargetUrl(url);
  if (!safeUrl) return '';
  return `${FACEBOOK_SHARE_BASE_URL}?u=${encodeURIComponent(safeUrl)}`;
}

/**
 * Build a mailto: share URL with sanitized subject and body.
 */
export function buildEmailShareUrl(title, text) {
  const cleanTitle = sanitizeShareText(title) || DEFAULT_SHARE_TITLE;
  const cleanBody =
    sanitizeShareText(text, { allowNewlines: true }) || cleanTitle;
  return `mailto:?subject=${encodeURIComponent(cleanTitle)}&body=${encodeURIComponent(cleanBody)}`;
}

/**
 * Build the sanitized share payload and multi-channel share URLs for a post or form.
 */
export function buildSharePayload(entity, options = {}) {
  if (!entity || typeof entity !== 'object' || Array.isArray(entity)) {
    return null;
  }

  const entityType = options.entityType === 'form' ? 'form' : 'post';
  const fallbackTitle =
    entityType === 'form' ? DEFAULT_FORM_SHARE_TITLE : DEFAULT_SHARE_TITLE;
  const title = sanitizeShareText(entity.title) || fallbackTitle;
  const url = buildEntityDeepLink(entity, { ...options, entityType });
  const text = `${title}\n${url}`;
  const whatsappUrl = `${WHATSAPP_SHARE_BASE_URL}?text=${encodeURIComponent(text)}`;
  const facebookUrl = buildFacebookShareUrl(url);
  const emailUrl = buildEmailShareUrl(title, text);

  return {
    title,
    url,
    text,
    whatsappUrl,
    facebookUrl,
    emailUrl,
  };
}

/**
 * Build the multi-channel share payload specifically for an engagement form.
 */
export function buildFormSharePayload(form, options = {}) {
  return buildSharePayload(form, { ...options, entityType: 'form' });
}

/**
 * Convenience helper returning only the encoded https://wa.me/?text=... URL.
 */
export function buildWhatsAppShareUrl(entity, options = {}) {
  return buildSharePayload(entity, options)?.whatsappUrl ?? '';
}

/**
 * Determine whether the Web Share API is available and accepts the payload.
 */
export function canUseWebShare(navigatorObj, shareData) {
  if (!navigatorObj || typeof navigatorObj.share !== 'function') {
    return false;
  }
  if (typeof navigatorObj.canShare === 'function' && shareData) {
    try {
      return Boolean(navigatorObj.canShare(shareData));
    } catch {
      return false;
    }
  }
  return true;
}

const MOBILE_USER_AGENT_RE =
  /Android|iPhone|iPad|iPod|IEMobile|Opera Mini|Mobile/i;

/**
 * Detect whether the current runtime appears to be a mobile phone or tablet.
 */
export function isMobileDevice(navigatorObj, windowObj) {
  const nav =
    navigatorObj !== undefined
      ? navigatorObj
      : typeof navigator !== 'undefined'
        ? navigator
        : null;

  const win =
    windowObj !== undefined
      ? windowObj
      : typeof window !== 'undefined'
        ? window
        : null;

  if (nav?.userAgentData?.mobile === true) {
    return true;
  }

  const userAgent = typeof nav?.userAgent === 'string' ? nav.userAgent : '';
  if (MOBILE_USER_AGENT_RE.test(userAgent)) {
    return true;
  }

  if (win && typeof win.matchMedia === 'function') {
    try {
      return Boolean(win.matchMedia('(pointer: coarse)')?.matches);
    } catch {
      return false;
    }
  }

  return false;
}

/**
 * Determine whether clicking Share should directly open the device's native mobile Share Sheet.
 */
export function shouldUseNativeMobileShare({
  navigatorObj,
  windowObj,
  shareData,
} = {}) {
  const nav =
    navigatorObj !== undefined
      ? navigatorObj
      : typeof navigator !== 'undefined'
        ? navigator
        : null;

  return (
    canUseWebShare(nav, shareData) && isMobileDevice(nav, windowObj)
  );
}

/**
 * Execute the unified Share button action: native Share Sheet on mobile devices,
 * falling back to opening the share menu on desktop or if native sharing errors.
 */
export async function executeShareButtonAction(entity, options = {}) {
  const payload = buildSharePayload(entity, options);
  if (!payload) {
    return {
      action: 'none',
      method: 'none',
      status: 'invalid',
      payload: null,
    };
  }

  const navigatorObj =
    options.navigatorObj !== undefined
      ? options.navigatorObj
      : typeof navigator !== 'undefined'
        ? navigator
        : null;

  const windowObj =
    options.windowObj !== undefined
      ? options.windowObj
      : typeof window !== 'undefined'
        ? window
        : null;

  const isAbsoluteHttp = /^https?:\/\//i.test(payload.url);
  const webShareData = isAbsoluteHttp
    ? { title: payload.title, text: payload.title, url: payload.url }
    : { title: payload.title, text: payload.text };

  if (
    shouldUseNativeMobileShare({
      navigatorObj,
      windowObj,
      shareData: webShareData,
    })
  ) {
    try {
      await navigatorObj.share(webShareData);
      return {
        action: 'native-shared',
        method: 'web-share',
        status: 'shared',
        payload,
      };
    } catch (error) {
      if (error?.name === 'AbortError') {
        return {
          action: 'cancelled',
          method: 'web-share',
          status: 'cancelled',
          payload,
        };
      }
      return {
        action: 'open-menu',
        method: 'menu',
        status: 'fallback',
        payload,
      };
    }
  }

  return {
    action: 'open-menu',
    method: 'menu',
    status: 'toggle',
    payload,
  };
}

/**
 * Copy a validated share URL to the clipboard with an execCommand fallback.
 */
export async function copyShareLink(url, options = {}) {
  const safeUrl = sanitizeShareTargetUrl(url);
  if (!safeUrl) {
    return { copied: false, method: 'none' };
  }

  const clipboardObj =
    options.clipboardObj !== undefined
      ? options.clipboardObj
      : typeof navigator !== 'undefined'
        ? navigator.clipboard
        : null;

  if (clipboardObj && typeof clipboardObj.writeText === 'function') {
    try {
      await clipboardObj.writeText(safeUrl);
      return { copied: true, method: 'clipboard' };
    } catch {
      // Fall through to execCommand fallback
    }
  }

  const documentObj =
    options.documentObj !== undefined
      ? options.documentObj
      : typeof document !== 'undefined'
        ? document
        : null;

  if (
    documentObj &&
    documentObj.body &&
    typeof documentObj.createElement === 'function' &&
    typeof documentObj.execCommand === 'function'
  ) {
    let textarea = null;
    try {
      textarea = documentObj.createElement('textarea');
      textarea.value = safeUrl;
      textarea.setAttribute?.('readonly', '');
      if (textarea.style) {
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
      }
      documentObj.body.appendChild(textarea);
      textarea.select?.();
      const ok = Boolean(documentObj.execCommand('copy'));
      return {
        copied: ok,
        method: ok ? 'execCommand' : 'failed',
      };
    } catch {
      return { copied: false, method: 'failed' };
    } finally {
      if (textarea && typeof documentObj.body.removeChild === 'function') {
        try {
          documentObj.body.removeChild(textarea);
        } catch {
          // Ignore cleanup errors
        }
      }
    }
  }

  return { copied: false, method: 'failed' };
}

/**
 * Trigger sharing for a post or form via WhatsApp deep link or Web Share API fallback/preference.
 */
export async function sharePost(entity, options = {}) {
  const payload = buildSharePayload(entity, options);
  if (!payload) {
    return { method: 'none', status: 'invalid', payload: null };
  }

  const navigatorObj =
    options.navigatorObj !== undefined
      ? options.navigatorObj
      : typeof navigator !== 'undefined'
        ? navigator
        : null;

  const openWindow =
    options.openWindow !== undefined
      ? options.openWindow
      : typeof window !== 'undefined' && typeof window.open === 'function'
        ? window.open.bind(window)
        : null;

  const isAbsoluteHttp = /^https?:\/\//i.test(payload.url);
  const webShareData = isAbsoluteHttp
    ? { title: payload.title, text: payload.title, url: payload.url }
    : { title: payload.title, text: payload.text };

  if (
    options.preferWebShare === true &&
    canUseWebShare(navigatorObj, webShareData)
  ) {
    try {
      await navigatorObj.share(webShareData);
      return { method: 'web-share', status: 'shared', payload };
    } catch (error) {
      if (error?.name === 'AbortError') {
        return { method: 'web-share', status: 'cancelled', payload };
      }
      const opened = openWindow
        ? openWindow(payload.whatsappUrl, '_blank', 'noopener,noreferrer')
        : null;
      return {
        method: 'whatsapp',
        status: opened ? 'opened' : 'fallback-href',
        payload,
      };
    }
  }

  const opened = openWindow
    ? openWindow(payload.whatsappUrl, '_blank', 'noopener,noreferrer')
    : null;
  if (opened) {
    return { method: 'whatsapp', status: 'opened', payload };
  }

  if (canUseWebShare(navigatorObj, webShareData)) {
    try {
      await navigatorObj.share(webShareData);
      return { method: 'web-share', status: 'shared', payload };
    } catch (error) {
      if (error?.name === 'AbortError') {
        return { method: 'web-share', status: 'cancelled', payload };
      }
    }
  }

  return { method: 'whatsapp', status: 'fallback-href', payload };
}
