const fs = require('node:fs');
const path = require('node:path');

const SITE_NAME = 'لجنة أولياء أمور الطلاب - مدرسة المحجر الابتدائية';
const DEFAULT_SITE_DESCRIPTION =
  'المنصة الرقمية للتواصل المجتمعي – لجنة أولياء أمور الطلاب في مدرسة المحجر الابتدائية.';
const MAX_PREVIEW_DESCRIPTION_LENGTH = 200;
const SAFE_POST_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;
const YOUTUBE_ID_RE = /^[A-Za-z0-9_-]{11}$/;
const YOUTUBE_HOSTS = new Set([
  'youtube.com',
  'www.youtube.com',
  'm.youtube.com',
  'youtu.be',
  'www.youtube-nocookie.com',
]);
const UNSAFE_URL_RE = /[\s\x00-\x1f\x7f<>"']/;
const LOCALHOST_HOSTS = new Set(['localhost', '127.0.0.1', '::1', '[::1]']);

const EXISTING_HEAD_META_PATTERNS = [
  /<title\b[^>]*>[\s\S]*?<\/title>/gi,
  /<link\b[^>]*\brel\s*=\s*(['"])canonical\1[^>]*>/gi,
  /<meta\b[^>]*\bname\s*=\s*(['"])description\1[^>]*>/gi,
  /<meta\b[^>]*\bproperty\s*=\s*(['"])og:(?:type|title|description|image|image:secure_url|image:type|image:width|image:height|image:alt|url)\1[^>]*>/gi,
  /<meta\b[^>]*\bproperty\s*=\s*(['"])article:published_time\1[^>]*>/gi,
  /<meta\b[^>]*\bname\s*=\s*(['"])twitter:(?:card|title|description|image|image:alt)\1[^>]*>/gi,
];

let cachedDiskTemplateHtml = null;
const cachedOriginTemplates = new Map();

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#x27;');
}

function normalizeOrigin(rawOrigin) {
  if (typeof rawOrigin !== 'string') return '';
  const candidate = rawOrigin.trim().replace(/\/+$/, '');
  if (!candidate || UNSAFE_URL_RE.test(candidate)) return '';

  let parsed;
  try {
    parsed = new URL(candidate);
  } catch {
    return '';
  }

  const protocol = parsed.protocol.toLowerCase();
  const host = (parsed.hostname || '').toLowerCase();
  if (!host || parsed.username || parsed.password) return '';
  if (protocol === 'https:') {
    return `${protocol}//${parsed.host}`;
  }
  if (protocol === 'http:' && LOCALHOST_HOSTS.has(host)) {
    return `${protocol}//${parsed.host}`;
  }
  return '';
}

function sanitizeHttpUrl(rawUrl) {
  if (typeof rawUrl !== 'string') return '';
  const candidate = rawUrl.trim();
  if (!candidate || UNSAFE_URL_RE.test(candidate)) return '';

  let parsed;
  try {
    parsed = new URL(candidate);
  } catch {
    return '';
  }

  const protocol = parsed.protocol.toLowerCase();
  if (protocol !== 'http:' && protocol !== 'https:') return '';
  if (parsed.username || parsed.password) return '';
  return parsed.toString();
}

function truncateDescription(text, maxLength = MAX_PREVIEW_DESCRIPTION_LENGTH) {
  const cleaned = String(text ?? '')
    .replace(/\s+/g, ' ')
    .trim();
  if (!cleaned) return '';
  if (cleaned.length <= maxLength) return cleaned;
  const cutoff = maxLength - 1;
  let sliced = cleaned.slice(0, cutoff);
  const lastSpace = sliced.lastIndexOf(' ');
  if (lastSpace >= Math.floor(cutoff * 0.6)) {
    sliced = sliced.slice(0, lastSpace);
  }
  return `${sliced.trimEnd()}…`;
}

function extractYoutubeVideoId(rawUrl) {
  const safe = sanitizeHttpUrl(rawUrl);
  if (!safe) return '';
  let parsed;
  try {
    parsed = new URL(safe);
  } catch {
    return '';
  }
  const host = (parsed.hostname || '').toLowerCase();
  if (!YOUTUBE_HOSTS.has(host)) return '';

  const segments = parsed.pathname.split('/').filter(Boolean);
  let videoId = '';
  if (host === 'youtu.be' && segments.length > 0) {
    videoId = segments[0];
  } else if (
    segments.length >= 2 &&
    (segments[0] === 'shorts' || segments[0] === 'embed' || segments[0] === 'live')
  ) {
    videoId = segments[1];
  } else {
    videoId = parsed.searchParams.get('v') || '';
  }
  return YOUTUBE_ID_RE.test(videoId) ? videoId : '';
}

function inferImageMimeType(imageUrl) {
  let parsed;
  try {
    parsed = new URL(imageUrl, 'https://localhost');
  } catch {
    return '';
  }
  const queryFmt = (parsed.searchParams.get('format') || '').trim().toLowerCase();
  if (queryFmt === 'jpeg' || queryFmt === 'jpg') return 'image/jpeg';
  const lowerPath = (parsed.pathname || '').toLowerCase();
  if (lowerPath.endsWith('.jpg') || lowerPath.endsWith('.jpeg')) return 'image/jpeg';
  if (lowerPath.endsWith('.png')) return 'image/png';
  if (lowerPath.endsWith('.webp')) return 'image/webp';
  if (lowerPath.endsWith('.gif')) return 'image/gif';
  return '';
}

function formatLocalMediaPreviewPath(mediaPath) {
  if (mediaPath.startsWith('/api/media/images/') && mediaPath.endsWith('.webp')) {
    return `${mediaPath}?format=jpeg`;
  }
  return mediaPath;
}

function resolveSiteOrigin(req) {
  const headers = req?.headers || {};
  const rawProto = String(headers['x-forwarded-proto'] || 'https')
    .split(',')[0]
    .trim()
    .toLowerCase();
  const proto = rawProto === 'http' || rawProto === 'https' ? rawProto : 'https';
  const rawHost = String(headers['x-forwarded-host'] || headers.host || '')
    .split(',')[0]
    .trim();
  if (!rawHost || UNSAFE_URL_RE.test(rawHost)) {
    return '';
  }
  const candidate = `${proto}://${rawHost}`;
  try {
    const parsed = new URL(candidate);
    if (parsed.username || parsed.password || !parsed.host) return '';
    return `${parsed.protocol}//${parsed.host}`;
  } catch {
    return '';
  }
}

function resolvePreviewImageUrl(post, { siteOrigin = '', apiBaseUrl = '' } = {}) {
  const cleanSiteOrigin = siteOrigin ? siteOrigin.replace(/\/+$/, '') : '';
  const cleanMediaOrigin = normalizeOrigin(apiBaseUrl) || cleanSiteOrigin;

  const candidates = [];
  let youtubeVideoId = '';
  if (post && typeof post === 'object') {
    const primary = post.imageUrl ?? post.image_url ?? '';
    if (typeof primary === 'string' && primary.trim()) {
      candidates.push(primary.trim());
    }

    const mediaLinks = post.mediaLinks ?? post.media_links ?? [];
    if (Array.isArray(mediaLinks)) {
      for (const item of mediaLinks) {
        if (!item || typeof item !== 'object') continue;
        const mType = String(item.mediaType ?? item.media_type ?? '')
          .trim()
          .toLowerCase();
        const linkUrl =
          item.canonicalUrl ??
          item.canonical_url ??
          item.embedUrl ??
          item.embed_url ??
          item.url ??
          '';
        if (typeof linkUrl !== 'string' || !linkUrl.trim()) continue;
        const trimmedUrl = linkUrl.trim();
        if (mType === 'image') {
          candidates.push(trimmedUrl);
        } else if (!youtubeVideoId) {
          const ytId = extractYoutubeVideoId(trimmedUrl);
          if (ytId) {
            youtubeVideoId = ytId;
          }
        }
      }
    }
  }

  for (const candidate of candidates) {
    if (UNSAFE_URL_RE.test(candidate)) continue;
    if (candidate.startsWith('/api/media/')) {
      const previewPath = formatLocalMediaPreviewPath(candidate);
      const imageUrl = cleanMediaOrigin ? `${cleanMediaOrigin}${previewPath}` : previewPath;
      return {
        imageUrl,
        hasCustomImage: true,
        mimeType: inferImageMimeType(imageUrl),
        width: null,
        height: null,
      };
    }
    if (candidate.startsWith('/') && !candidate.startsWith('//')) {
      const imageUrl = cleanSiteOrigin ? `${cleanSiteOrigin}${candidate}` : candidate;
      return {
        imageUrl,
        hasCustomImage: true,
        mimeType: inferImageMimeType(imageUrl),
        width: null,
        height: null,
      };
    }
    const safeAbs = sanitizeHttpUrl(candidate);
    if (safeAbs) {
      return {
        imageUrl: safeAbs,
        hasCustomImage: true,
        mimeType: inferImageMimeType(safeAbs),
        width: null,
        height: null,
      };
    }
  }

  if (youtubeVideoId) {
    return {
      imageUrl: `https://i.ytimg.com/vi/${youtubeVideoId}/hqdefault.jpg`,
      hasCustomImage: true,
      mimeType: 'image/jpeg',
      width: 480,
      height: 360,
    };
  }

  return {
    imageUrl: cleanSiteOrigin ? `${cleanSiteOrigin}/logo.jpg` : '/logo.jpg',
    hasCustomImage: false,
    mimeType: 'image/jpeg',
    width: null,
    height: null,
  };
}

function buildPostPreviewHtml(templateHtml, post, { siteOrigin = '', apiBaseUrl = '' } = {}) {
  const cleanSiteOrigin = siteOrigin ? siteOrigin.replace(/\/+$/, '') : '';
  const postId = String(post?.id ?? '').trim();
  const encodedId = encodeURIComponent(postId);
  const canonicalUrl = cleanSiteOrigin
    ? `${cleanSiteOrigin}/posts/${encodedId}`
    : `/posts/${encodedId}`;

  const rawTitle =
    String(post?.title ?? '')
      .replace(/\s+/g, ' ')
      .trim() || SITE_NAME;
  const pageTitle = rawTitle === SITE_NAME ? SITE_NAME : `${rawTitle} | ${SITE_NAME}`;
  const rawDesc =
    post?.summary ?? post?.description ?? post?.content ?? '';
  const description = truncateDescription(rawDesc) || DEFAULT_SITE_DESCRIPTION;

  const { imageUrl, hasCustomImage, mimeType, width, height } = resolvePreviewImageUrl(post, {
    siteOrigin: cleanSiteOrigin,
    apiBaseUrl,
  });
  const twitterCard = hasCustomImage ? 'summary_large_image' : 'summary';
  const publishedAt = String(
    post?.publishedAt ?? post?.published_at ?? post?.createdAt ?? post?.created_at ?? ''
  ).trim();

  const metaLines = [
    `  <meta name="description" content="${escapeHtml(description)}" />`,
    '  <meta property="og:type" content="article" />',
    `  <meta property="og:title" content="${escapeHtml(rawTitle)}" />`,
    `  <meta property="og:description" content="${escapeHtml(description)}" />`,
    `  <meta property="og:url" content="${escapeHtml(canonicalUrl)}" />`,
    `  <meta property="og:image" content="${escapeHtml(imageUrl)}" />`,
  ];
  if (imageUrl.startsWith('https://')) {
    metaLines.push(
      `  <meta property="og:image:secure_url" content="${escapeHtml(imageUrl)}" />`
    );
  }
  if (mimeType) {
    metaLines.push(
      `  <meta property="og:image:type" content="${escapeHtml(mimeType)}" />`
    );
  }
  if (width && height) {
    metaLines.push(`  <meta property="og:image:width" content="${width}" />`);
    metaLines.push(`  <meta property="og:image:height" content="${height}" />`);
  }
  metaLines.push(`  <meta property="og:image:alt" content="${escapeHtml(rawTitle)}" />`);
  if (publishedAt) {
    metaLines.push(
      `  <meta property="article:published_time" content="${escapeHtml(publishedAt)}" />`
    );
  }
  metaLines.push(
    `  <meta name="twitter:card" content="${escapeHtml(twitterCard)}" />`,
    `  <meta name="twitter:title" content="${escapeHtml(rawTitle)}" />`,
    `  <meta name="twitter:description" content="${escapeHtml(description)}" />`,
    `  <meta name="twitter:image" content="${escapeHtml(imageUrl)}" />`,
    `  <meta name="twitter:image:alt" content="${escapeHtml(rawTitle)}" />`,
    `  <link rel="canonical" href="${escapeHtml(canonicalUrl)}" />`,
    `  <title>${escapeHtml(pageTitle)}</title>`
  );

  const injectedBlock = `${metaLines.join('\n')}\n`;

  let cleanedHtml = String(templateHtml ?? '');
  for (const pattern of EXISTING_HEAD_META_PATTERNS) {
    cleanedHtml = cleanedHtml.replace(pattern, '');
  }
  cleanedHtml = cleanedHtml.replace(/\n{3,}/g, '\n\n');

  if (/<\/head>/i.test(cleanedHtml)) {
    return cleanedHtml.replace(/<\/head>/i, `${injectedBlock}</head>`);
  }
  if (/<body\b[^>]*>/i.test(cleanedHtml)) {
    return cleanedHtml.replace(/<body\b[^>]*>/i, (m) => `<head>\n${injectedBlock}</head>${m}`);
  }
  return `<head>\n${injectedBlock}</head>\n${cleanedHtml}`;
}

async function defaultLoadTemplateHtml(siteOrigin, fetchImpl) {
  if (cachedDiskTemplateHtml) {
    return cachedDiskTemplateHtml;
  }

  const candidatePaths = [
    path.resolve(process.cwd(), 'frontend', 'dist', 'index.html'),
    path.resolve(__dirname, '..', 'frontend', 'dist', 'index.html'),
  ];
  for (const diskPath of candidatePaths) {
    try {
      if (fs.existsSync(diskPath)) {
        const html = fs.readFileSync(diskPath, 'utf-8');
        if (html) {
          cachedDiskTemplateHtml = html;
          return html;
        }
      }
    } catch {
      // Try next path or network fallback
    }
  }

  if (siteOrigin && typeof fetchImpl === 'function') {
    if (cachedOriginTemplates.has(siteOrigin)) {
      return cachedOriginTemplates.get(siteOrigin);
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 3500);
    try {
      const resp = await fetchImpl(`${siteOrigin}/index.html`, {
        signal: controller.signal,
        headers: { Accept: 'text/html' },
      });
      if (resp && resp.ok) {
        const html = await resp.text();
        if (html) {
          cachedOriginTemplates.set(siteOrigin, html);
          return html;
        }
      }
    } catch {
      // Fall through to minimal HTML
    } finally {
      clearTimeout(timer);
    }
  }

  return `<!DOCTYPE html><html lang="ar" dir="rtl"><head><title>${SITE_NAME}</title></head><body><div id="root"></div></body></html>`;
}

function applySecurityHeaders(res, cacheControlValue) {
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.setHeader('Cache-Control', cacheControlValue);
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('X-Frame-Options', 'DENY');
  res.setHeader('Referrer-Policy', 'strict-origin-when-cross-origin');
}

function createPostPreviewHandler({
  fetchImpl = typeof fetch === 'function' ? fetch : null,
  loadTemplateHtml = null,
  apiBaseUrlOverride = null,
} = {}) {
  return async function postPreviewHandler(req, res) {
    const siteOrigin = resolveSiteOrigin(req);
    const rawId = Array.isArray(req?.query?.id) ? req.query.id[0] : req?.query?.id;
    const postId = typeof rawId === 'string' ? rawId.trim() : '';

    const templateHtml =
      typeof loadTemplateHtml === 'function'
        ? await loadTemplateHtml(siteOrigin)
        : await defaultLoadTemplateHtml(siteOrigin, fetchImpl);

    const resolvedApiBase = normalizeOrigin(
      apiBaseUrlOverride ??
        process.env.MAHJAR_API_BASE_URL ??
        process.env.VITE_API_BASE_URL ??
        ''
    );

    if (!SAFE_POST_ID_RE.test(postId) || !resolvedApiBase || typeof fetchImpl !== 'function') {
      applySecurityHeaders(res, 'no-cache');
      return res.status(200).send(templateHtml);
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const apiUrl = `${resolvedApiBase}/api/posts/${encodeURIComponent(postId)}`;
      const apiResp = await fetchImpl(apiUrl, {
        signal: controller.signal,
        headers: { Accept: 'application/json' },
      });
      if (!apiResp || !apiResp.ok) {
        applySecurityHeaders(res, 'no-cache');
        return res.status(200).send(templateHtml);
      }

      const post = await apiResp.json();
      if (!post || typeof post !== 'object' || Array.isArray(post) || post.id === undefined) {
        applySecurityHeaders(res, 'no-cache');
        return res.status(200).send(templateHtml);
      }

      const rendered = buildPostPreviewHtml(templateHtml, post, {
        siteOrigin,
        apiBaseUrl: resolvedApiBase,
      });
      applySecurityHeaders(res, 'public, s-maxage=60, stale-while-revalidate=300');
      return res.status(200).send(rendered);
    } catch {
      applySecurityHeaders(res, 'no-cache');
      return res.status(200).send(templateHtml);
    } finally {
      clearTimeout(timer);
    }
  };
}

const defaultHandler = createPostPreviewHandler();
defaultHandler.buildPostPreviewHtml = buildPostPreviewHtml;
defaultHandler.resolvePreviewImageUrl = resolvePreviewImageUrl;
defaultHandler.resolveSiteOrigin = resolveSiteOrigin;
defaultHandler.createPostPreviewHandler = createPostPreviewHandler;

module.exports = defaultHandler;
