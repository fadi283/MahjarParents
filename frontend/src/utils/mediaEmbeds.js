export const RAW_AV_EXTENSIONS = new Set([
  '.mp4',
  '.mov',
  '.avi',
  '.mkv',
  '.webm',
  '.m4v',
  '.3gp',
  '.mp3',
  '.wav',
  '.ogg',
  '.m4a',
  '.aac',
  '.flac',
  '.wma',
]);

const YOUTUBE_HOSTS = new Set([
  'youtube.com',
  'www.youtube.com',
  'm.youtube.com',
  'youtu.be',
  'www.youtube-nocookie.com',
]);

const VIMEO_HOSTS = new Set([
  'vimeo.com',
  'www.vimeo.com',
  'player.vimeo.com',
]);

const SOUNDCLOUD_PAGE_HOSTS = new Set([
  'soundcloud.com',
  'www.soundcloud.com',
  'm.soundcloud.com',
]);

const SOUNDCLOUD_HOSTS = new Set([
  ...SOUNDCLOUD_PAGE_HOSTS,
  'w.soundcloud.com',
]);

const GOOGLE_DRIVE_HOSTS = new Set(['drive.google.com']);

const YOUTUBE_ID_RE = /^[A-Za-z0-9_-]{11}$/;
const VIMEO_ID_RE = /^\d+$/;
const DRIVE_ID_RE = /^[A-Za-z0-9_-]{10,}$/;

function getPathExtension(pathname) {
  const cleanPath = (pathname || '').split('?')[0].split('#')[0];
  const lastSegment = cleanPath.split('/').pop() || '';
  const dotIdx = lastSegment.lastIndexOf('.');
  if (dotIdx <= 0) return '';
  return lastSegment.slice(dotIdx).toLowerCase();
}

function isDisallowedAssetExtension(pathname) {
  const ext = getPathExtension(pathname);
  return ext === '.svg' || RAW_AV_EXTENSIONS.has(ext);
}

/**
 * Validate and sanitize an image URL to allow only HTTPS URLs or safe root-relative paths.
 * Rejects SVG, raw audio/video files, embedded credentials, and path traversal.
 */
export function sanitizeImageUrl(rawUrl) {
  if (typeof rawUrl !== 'string') return null;
  const trimmed = rawUrl.trim();
  if (!trimmed || /[\s\u0000-\u001f]/.test(trimmed)) {
    return null;
  }

  if (trimmed.startsWith('/')) {
    if (trimmed.startsWith('//')) {
      return null;
    }
    const pathOnly = trimmed.split('?')[0].split('#')[0];
    const segments = pathOnly.split('/');
    if (segments.includes('..') || segments.includes('.')) {
      return null;
    }
    if (isDisallowedAssetExtension(pathOnly)) {
      return null;
    }
    return trimmed;
  }

  let parsed;
  try {
    parsed = new URL(trimmed);
  } catch {
    return null;
  }

  if (parsed.protocol.toLowerCase() !== 'https:') {
    return null;
  }
  if (parsed.username || parsed.password || !parsed.hostname) {
    return null;
  }
  if (isDisallowedAssetExtension(parsed.pathname)) {
    return null;
  }

  return trimmed;
}

function parseYouTubeEmbed(parsed) {
  const host = parsed.hostname.toLowerCase();
  const segments = parsed.pathname.split('/').filter(Boolean);
  let videoId = '';

  if (host === 'youtu.be' && segments.length > 0) {
    videoId = segments[0];
  } else if (parsed.pathname === '/watch') {
    videoId = parsed.searchParams.get('v') || '';
  } else if (
    segments.length >= 2 &&
    (segments[0] === 'shorts' ||
      segments[0] === 'embed' ||
      segments[0] === 'live')
  ) {
    videoId = segments[1];
  }

  if (!YOUTUBE_ID_RE.test(videoId)) {
    return null;
  }

  return {
    mediaType: 'video',
    provider: 'youtube',
    providerLabel: 'يوتيوب',
    canonicalUrl: `https://www.youtube.com/watch?v=${videoId}`,
    embedUrl: `https://www.youtube-nocookie.com/embed/${videoId}`,
  };
}

function parseVimeoEmbed(parsed) {
  const host = parsed.hostname.toLowerCase();
  const segments = parsed.pathname.split('/').filter(Boolean);
  let videoId = '';

  if (host === 'player.vimeo.com') {
    if (segments.length >= 2 && segments[0] === 'video') {
      videoId = segments[1];
    }
  } else if (segments.length > 0) {
    videoId = segments[segments.length - 1];
  }

  if (!VIMEO_ID_RE.test(videoId)) {
    return null;
  }

  return {
    mediaType: 'video',
    provider: 'vimeo',
    providerLabel: 'فيميو',
    canonicalUrl: `https://vimeo.com/${videoId}`,
    embedUrl: `https://player.vimeo.com/video/${videoId}`,
  };
}

function parseSoundCloudEmbed(parsed) {
  const host = parsed.hostname.toLowerCase();
  let trackPath = parsed.pathname;

  if (host === 'w.soundcloud.com') {
    if (parsed.pathname.replace(/\/+$/, '') !== '/player') {
      return null;
    }
    const innerUrl = (parsed.searchParams.get('url') || '').trim();
    if (!innerUrl) {
      return null;
    }
    let innerParsed;
    try {
      innerParsed = new URL(innerUrl);
    } catch {
      return null;
    }
    const innerHost = innerParsed.hostname.toLowerCase();
    if (
      innerParsed.protocol.toLowerCase() !== 'https:' ||
      innerParsed.username ||
      innerParsed.password ||
      !SOUNDCLOUD_PAGE_HOSTS.has(innerHost)
    ) {
      return null;
    }
    trackPath = innerParsed.pathname;
  }

  const segments = trackPath.split('/').filter(Boolean);
  if (segments.length === 0) {
    return null;
  }

  const canonicalUrl = `https://soundcloud.com/${segments.join('/')}`;
  const embedUrl = `https://w.soundcloud.com/player/?url=${encodeURIComponent(
    canonicalUrl
  )}&auto_play=false&show_teaser=false`;

  return {
    mediaType: 'audio',
    provider: 'soundcloud',
    providerLabel: 'ساوند كلاود',
    canonicalUrl,
    embedUrl,
  };
}

function parseGoogleDriveEmbed(parsed) {
  const segments = parsed.pathname.split('/').filter(Boolean);
  const cleanPath = parsed.pathname.replace(/\/+$/, '');
  let fileId = '';

  if (segments.length >= 3 && segments[0] === 'file' && segments[1] === 'd') {
    fileId = segments[2];
  } else if (cleanPath === '/open' || cleanPath === '/uc') {
    fileId = parsed.searchParams.get('id') || '';
  }

  if (!DRIVE_ID_RE.test(fileId)) {
    return null;
  }

  return {
    mediaType: 'audio',
    provider: 'google_drive',
    providerLabel: 'Google Drive',
    canonicalUrl: `https://drive.google.com/file/d/${fileId}/view`,
    embedUrl: `https://drive.google.com/file/d/${fileId}/preview`,
  };
}

/**
 * Resolve and normalize an allowlisted external video or audio URL into a safe HTTPS embed object.
 * Returns null for untrusted domains, non-HTTPS URLs, raw files, credentials, or type mismatches.
 */
export function resolveExternalMediaEmbed(input, explicitMediaType = null) {
  if (!input) return null;

  let rawUrl = '';
  let requestedType = explicitMediaType;
  let title = '';

  if (typeof input === 'string') {
    rawUrl = input;
  } else if (typeof input === 'object') {
    rawUrl =
      input.url ??
      input.embedUrl ??
      input.embed_url ??
      input.originalUrl ??
      input.original_url ??
      input.canonicalUrl ??
      input.canonical_url ??
      '';
    if (requestedType == null) {
      requestedType = input.mediaType ?? input.media_type ?? null;
    }
    title = typeof input.title === 'string' ? input.title.trim() : '';
  } else {
    return null;
  }

  if (typeof rawUrl !== 'string') return null;
  const cleaned = rawUrl.trim();
  if (!cleaned) return null;

  let parsed;
  try {
    parsed = new URL(cleaned);
  } catch {
    return null;
  }

  if (parsed.protocol.toLowerCase() !== 'https:') {
    return null;
  }
  if (parsed.username || parsed.password || !parsed.hostname) {
    return null;
  }

  const host = parsed.hostname.toLowerCase();
  let resolved = null;

  if (YOUTUBE_HOSTS.has(host)) {
    resolved = parseYouTubeEmbed(parsed);
  } else if (VIMEO_HOSTS.has(host)) {
    resolved = parseVimeoEmbed(parsed);
  } else if (SOUNDCLOUD_HOSTS.has(host)) {
    resolved = parseSoundCloudEmbed(parsed);
  } else if (GOOGLE_DRIVE_HOSTS.has(host)) {
    resolved = parseGoogleDriveEmbed(parsed);
  }

  if (!resolved) {
    return null;
  }

  if (requestedType != null && String(requestedType).trim()) {
    const normalizedRequested = String(requestedType).trim().toLowerCase();
    if (
      (normalizedRequested !== 'video' && normalizedRequested !== 'audio') ||
      normalizedRequested !== resolved.mediaType
    ) {
      return null;
    }
  }

  return {
    ...resolved,
    title,
    hostedExternally: true,
  };
}

/**
 * Extract deduplicated safe lazy-loadable images and allowlisted external embeds from a post object.
 */
export function extractPostMedia(post) {
  if (!post || typeof post !== 'object') {
    return { images: [], embeds: [] };
  }

  const images = [];
  const seenImageUrls = new Set();

  const addImageCandidate = (candidate) => {
    if (!candidate) return;
    let rawUrl = '';
    let alt = '';
    let caption = '';
    let width;
    let height;

    if (typeof candidate === 'string') {
      rawUrl = candidate;
    } else if (typeof candidate === 'object') {
      rawUrl = candidate.url ?? candidate.src ?? candidate.imageUrl ?? candidate.image_url ?? '';
      alt = typeof candidate.alt === 'string' ? candidate.alt.trim() : '';
      caption = typeof candidate.caption === 'string' ? candidate.caption.trim() : '';
      width = candidate.width;
      height = candidate.height;
    }

    const safeUrl = sanitizeImageUrl(rawUrl);
    if (!safeUrl || seenImageUrls.has(safeUrl)) {
      return;
    }
    seenImageUrls.add(safeUrl);
    images.push({
      url: safeUrl,
      alt: alt || (typeof post.title === 'string' ? post.title.trim() : ''),
      caption,
      width,
      height,
    });
  };

  addImageCandidate(post.imageUrl ?? post.image_url);

  const extraImages = post.images ?? post.gallery;
  if (Array.isArray(extraImages)) {
    for (const item of extraImages) {
      addImageCandidate(item);
    }
  }

  const embeds = [];
  const seenEmbedUrls = new Set();

  const addEmbedCandidate = (candidate, explicitType = null) => {
    const resolved = resolveExternalMediaEmbed(candidate, explicitType);
    if (!resolved || seenEmbedUrls.has(resolved.embedUrl)) {
      return;
    }
    seenEmbedUrls.add(resolved.embedUrl);
    embeds.push(resolved);
  };

  const rawMediaLinks = post.mediaLinks ?? post.media_links;
  if (Array.isArray(rawMediaLinks)) {
    for (const item of rawMediaLinks) {
      addEmbedCandidate(item);
    }
  } else if (rawMediaLinks) {
    addEmbedCandidate(rawMediaLinks);
  }

  addEmbedCandidate(post.videoUrl ?? post.video_url, 'video');
  addEmbedCandidate(post.audioUrl ?? post.audio_url, 'audio');

  return { images, embeds };
}
