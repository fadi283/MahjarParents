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

export const ALLOWED_EXTERNAL_MEDIA_TYPES = [
  'video',
  'reel',
  'post',
  'image',
  'audio',
];

export const EXTERNAL_IMAGE_EXTENSIONS = new Set([
  '.jpg',
  '.jpeg',
  '.png',
  '.webp',
  '.gif',
  '.avif',
  '.bmp',
]);

export const MEDIA_TYPE_LABELS = {
  video: 'فيديو',
  reel: 'رييل',
  post: 'منشور',
  image: 'صورة',
  audio: 'صوت',
};

export const PROVIDER_LABELS = {
  youtube: 'يوتيوب',
  vimeo: 'فيميو',
  dailymotion: 'ديلي موشن',
  instagram: 'إنستغرام',
  facebook: 'فيسبوك',
  tiktok: 'تيك توك',
  x: 'إكس (تويتر)',
  threads: 'ثريدز',
  linkedin: 'لينكدإن',
  telegram: 'تيليغرام',
  soundcloud: 'ساوند كلاود',
  spotify: 'سبوتيفاي',
  google_drive: 'Google Drive',
  google_photos: 'صور Google',
  canva: 'Canva',
  external_image: 'صورة خارجية',
};

const YOUTUBE_HOSTS = new Set([
  'youtube.com',
  'www.youtube.com',
  'm.youtube.com',
  'youtu.be',
  'www.youtube-nocookie.com',
]);
const VIMEO_HOSTS = new Set(['vimeo.com', 'www.vimeo.com', 'player.vimeo.com']);
const DAILYMOTION_HOSTS = new Set([
  'dailymotion.com',
  'www.dailymotion.com',
  'dai.ly',
]);
const INSTAGRAM_HOSTS = new Set([
  'instagram.com',
  'www.instagram.com',
  'm.instagram.com',
  'instagr.am',
  'www.instagr.am',
]);
const FACEBOOK_PAGE_HOSTS = new Set([
  'facebook.com',
  'www.facebook.com',
  'm.facebook.com',
  'web.facebook.com',
  'fb.com',
  'www.fb.com',
]);
const FACEBOOK_HOSTS = new Set([...FACEBOOK_PAGE_HOSTS, 'fb.watch']);
const TIKTOK_SHORT_HOSTS = new Set(['vm.tiktok.com', 'vt.tiktok.com']);
const TIKTOK_HOSTS = new Set([
  'tiktok.com',
  'www.tiktok.com',
  'm.tiktok.com',
  ...TIKTOK_SHORT_HOSTS,
]);
const X_HOSTS = new Set([
  'x.com',
  'www.x.com',
  'mobile.x.com',
  'twitter.com',
  'www.twitter.com',
  'mobile.twitter.com',
]);
const THREADS_HOSTS = new Set([
  'threads.net',
  'www.threads.net',
  'threads.com',
  'www.threads.com',
]);
const LINKEDIN_HOSTS = new Set(['linkedin.com', 'www.linkedin.com']);
const TELEGRAM_HOSTS = new Set(['t.me', 'telegram.me']);
const SOUNDCLOUD_PAGE_HOSTS = new Set([
  'soundcloud.com',
  'www.soundcloud.com',
  'm.soundcloud.com',
]);
const SOUNDCLOUD_HOSTS = new Set([...SOUNDCLOUD_PAGE_HOSTS, 'w.soundcloud.com']);
const SPOTIFY_HOSTS = new Set(['open.spotify.com']);
const GOOGLE_DRIVE_HOSTS = new Set(['drive.google.com']);
const GOOGLE_PHOTOS_HOSTS = new Set(['photos.app.goo.gl', 'photos.google.com']);
const CANVA_HOSTS = new Set(['canva.com', 'www.canva.com']);

const YOUTUBE_ID_RE = /^[A-Za-z0-9_-]{11}$/;
const VIMEO_ID_RE = /^\d+$/;
const DRIVE_ID_RE = /^[A-Za-z0-9_-]{10,}$/;
const DAILYMOTION_ID_RE = /^[A-Za-z0-9]+$/;
const INSTAGRAM_SHORTCODE_RE = /^[A-Za-z0-9_-]{5,64}$/;
const NUMERIC_ID_RE = /^\d+$/;
const ALNUM_SLUG_RE = /^[A-Za-z0-9._-]+$/;
const HANDLE_RE = /^[A-Za-z0-9._-]{1,100}$/;
const SPOTIFY_ID_RE = /^[A-Za-z0-9]{10,64}$/;
const CANVA_ID_RE = /^[A-Za-z0-9_-]{6,64}$/;
const UNSAFE_MEDIA_URL_CHARS_RE = /[\s\u0000-\u001f\u007f<>\"']/;
const IPV4_RE = /^\d{1,3}(?:\.\d{1,3}){3}$/;

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

function hasTraversalSegments(pathname) {
  let decoded = pathname || '';
  try {
    decoded = decodeURIComponent(pathname || '');
  } catch {
    return true;
  }
  for (const candidate of [pathname || '', decoded]) {
    const segments = candidate.replace(/\\/g, '/').split('/');
    if (segments.includes('.') || segments.includes('..')) {
      return true;
    }
  }
  return false;
}

function isPublicHostname(host) {
  const cleaned = (host || '').trim().toLowerCase().replace(/\.+$/, '');
  if (
    !cleaned ||
    cleaned === 'localhost' ||
    cleaned.endsWith('.localhost') ||
    cleaned.endsWith('.local') ||
    cleaned.endsWith('.internal')
  ) {
    return false;
  }
  if (!cleaned.includes('.')) return false;
  if (IPV4_RE.test(cleaned)) return false;
  if (cleaned.includes(':') || cleaned.startsWith('[')) return false;
  return true;
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
    if (hasTraversalSegments(pathOnly)) {
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
  if (hasTraversalSegments(parsed.pathname)) {
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
  let isShorts = false;

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
    isShorts = segments[0] === 'shorts';
  }

  if (!YOUTUBE_ID_RE.test(videoId)) {
    return null;
  }

  return {
    mediaType: 'video',
    provider: 'youtube',
    providerLabel: PROVIDER_LABELS.youtube,
    canonicalUrl: isShorts
      ? `https://www.youtube.com/shorts/${videoId}`
      : `https://www.youtube.com/watch?v=${videoId}`,
    embedUrl: `https://www.youtube-nocookie.com/embed/${videoId}`,
    renderMode: 'iframe',
    aspectWidth: isShorts ? 9 : 16,
    aspectHeight: isShorts ? 16 : 9,
    allowedTypes: isShorts ? ['video', 'reel'] : ['video'],
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
    providerLabel: PROVIDER_LABELS.vimeo,
    canonicalUrl: `https://vimeo.com/${videoId}`,
    embedUrl: `https://player.vimeo.com/video/${videoId}`,
    renderMode: 'iframe',
    aspectWidth: 16,
    aspectHeight: 9,
    allowedTypes: ['video'],
  };
}

function parseDailymotionEmbed(parsed) {
  const host = parsed.hostname.toLowerCase();
  const segments = parsed.pathname.split('/').filter(Boolean);
  let videoId = '';

  if (host === 'dai.ly' && segments.length > 0) {
    videoId = segments[0];
  } else if (segments.length >= 2 && segments[0] === 'video') {
    videoId = segments[1];
  } else if (
    segments.length >= 3 &&
    segments[0] === 'embed' &&
    segments[1] === 'video'
  ) {
    videoId = segments[2];
  }

  if (!DAILYMOTION_ID_RE.test(videoId)) {
    return null;
  }

  return {
    mediaType: 'video',
    provider: 'dailymotion',
    providerLabel: PROVIDER_LABELS.dailymotion,
    canonicalUrl: `https://www.dailymotion.com/video/${videoId}`,
    embedUrl: `https://www.dailymotion.com/embed/video/${videoId}`,
    renderMode: 'iframe',
    aspectWidth: 16,
    aspectHeight: 9,
    allowedTypes: ['video'],
  };
}

function parseInstagramEmbed(parsed) {
  let segments = parsed.pathname.split('/').filter(Boolean);
  if (
    segments.length >= 3 &&
    segments[segments.length - 2] === 'embed' &&
    segments[segments.length - 1] === 'captioned'
  ) {
    segments = segments.slice(0, -2);
  } else if (
    segments.length >= 3 &&
    segments[segments.length - 1] === 'embed'
  ) {
    segments = segments.slice(0, -1);
  }

  let kind = '';
  let shortcode = '';
  if (
    segments.length >= 2 &&
    ['reel', 'reels', 'p', 'tv'].includes(segments[0])
  ) {
    [kind, shortcode] = segments;
  } else if (
    segments.length >= 3 &&
    ['reel', 'reels', 'p', 'tv'].includes(segments[1])
  ) {
    kind = segments[1];
    shortcode = segments[2];
  }

  if (kind && INSTAGRAM_SHORTCODE_RE.test(shortcode)) {
    const normKind = kind === 'reels' ? 'reel' : kind;
    const canonicalUrl = `https://www.instagram.com/${normKind}/${shortcode}/`;
    const embedUrl = `https://www.instagram.com/${normKind}/${shortcode}/embed/`;
    if (normKind === 'reel') {
      return {
        mediaType: 'reel',
        provider: 'instagram',
        providerLabel: PROVIDER_LABELS.instagram,
        canonicalUrl,
        embedUrl,
        renderMode: 'iframe',
        aspectWidth: 9,
        aspectHeight: 16,
        allowedTypes: ['reel', 'video'],
      };
    }
    if (normKind === 'p') {
      return {
        mediaType: 'post',
        provider: 'instagram',
        providerLabel: PROVIDER_LABELS.instagram,
        canonicalUrl,
        embedUrl,
        renderMode: 'iframe',
        allowedTypes: ['post', 'image', 'video', 'reel'],
      };
    }
    return {
      mediaType: 'video',
      provider: 'instagram',
      providerLabel: PROVIDER_LABELS.instagram,
      canonicalUrl,
      embedUrl,
      renderMode: 'iframe',
      aspectWidth: 9,
      aspectHeight: 16,
      allowedTypes: ['video', 'reel', 'post'],
    };
  }

  if (
    segments.length >= 3 &&
    segments[0] === 'stories' &&
    HANDLE_RE.test(segments[1]) &&
    ALNUM_SLUG_RE.test(segments[2])
  ) {
    return {
      mediaType: 'post',
      provider: 'instagram',
      providerLabel: PROVIDER_LABELS.instagram,
      canonicalUrl: `https://www.instagram.com/stories/${segments[1]}/${segments[2]}/`,
      embedUrl: '',
      renderMode: 'card',
      allowedTypes: ['post', 'reel', 'video', 'image'],
    };
  }

  if (
    segments.length >= 2 &&
    segments[0] === 'share' &&
    segments.slice(1).every((seg) => ALNUM_SLUG_RE.test(seg))
  ) {
    const mediaType =
      segments.length >= 3 && segments[1] === 'reel' ? 'reel' : 'post';
    return {
      mediaType,
      provider: 'instagram',
      providerLabel: PROVIDER_LABELS.instagram,
      canonicalUrl: `https://www.instagram.com/${segments.join('/')}/`,
      embedUrl: '',
      renderMode: 'card',
      allowedTypes: ['post', 'reel', 'video', 'image'],
    };
  }

  return null;
}

function parseFacebookEmbed(parsed, depth = 0) {
  const host = parsed.hostname.toLowerCase();
  const segments = parsed.pathname.split('/').filter(Boolean);
  const cleanPath = parsed.pathname.replace(/\/+$/, '');

  if (cleanPath === '/plugins/video.php' || cleanPath === '/plugins/post.php') {
    if (depth > 0) return null;
    const href = (parsed.searchParams.get('href') || '').trim();
    if (!href || UNSAFE_MEDIA_URL_CHARS_RE.test(href)) return null;
    let inner;
    try {
      inner = new URL(href);
    } catch {
      return null;
    }
    const innerHost = inner.hostname.toLowerCase();
    if (
      inner.protocol.toLowerCase() !== 'https:' ||
      inner.username ||
      inner.password ||
      hasTraversalSegments(inner.pathname) ||
      !FACEBOOK_HOSTS.has(innerHost)
    ) {
      return null;
    }
    return parseFacebookEmbed(inner, depth + 1);
  }

  if (host === 'fb.watch') {
    if (segments.length === 0 || !ALNUM_SLUG_RE.test(segments[0])) {
      return null;
    }
    return {
      mediaType: 'video',
      provider: 'facebook',
      providerLabel: PROVIDER_LABELS.facebook,
      canonicalUrl: `https://fb.watch/${segments[0]}/`,
      embedUrl: '',
      renderMode: 'card',
      allowedTypes: ['video', 'reel', 'post'],
    };
  }

  if (
    segments.length >= 2 &&
    segments[0] === 'share' &&
    segments.slice(1).every((seg) => ALNUM_SLUG_RE.test(seg))
  ) {
    const sub = segments[1];
    let shareType = 'post';
    if (sub === 'r' && segments.length >= 3) {
      shareType = 'reel';
    } else if (sub === 'v' && segments.length >= 3) {
      shareType = 'video';
    }
    return {
      mediaType: shareType,
      provider: 'facebook',
      providerLabel: PROVIDER_LABELS.facebook,
      canonicalUrl: `https://www.facebook.com/${segments.join('/')}/`,
      embedUrl: '',
      renderMode: 'card',
      allowedTypes: ['post', 'reel', 'video', 'image'],
    };
  }

  if (
    segments.length >= 2 &&
    (segments[0] === 'reel' || segments[0] === 'reels') &&
    ALNUM_SLUG_RE.test(segments[1])
  ) {
    const canonicalUrl = `https://www.facebook.com/reel/${segments[1]}`;
    return {
      mediaType: 'reel',
      provider: 'facebook',
      providerLabel: PROVIDER_LABELS.facebook,
      canonicalUrl,
      embedUrl: `https://www.facebook.com/plugins/video.php?href=${encodeURIComponent(
        canonicalUrl
      )}&show_text=false`,
      renderMode: 'iframe',
      aspectWidth: 9,
      aspectHeight: 16,
      allowedTypes: ['reel', 'video'],
    };
  }

  if (
    cleanPath === '/watch' ||
    cleanPath === '/video.php' ||
    cleanPath === '/video/video.php'
  ) {
    const videoId = (parsed.searchParams.get('v') || '').trim();
    if (!videoId || !ALNUM_SLUG_RE.test(videoId)) return null;
    const canonicalUrl = `https://www.facebook.com/watch/?v=${videoId}`;
    return {
      mediaType: 'video',
      provider: 'facebook',
      providerLabel: PROVIDER_LABELS.facebook,
      canonicalUrl,
      embedUrl: `https://www.facebook.com/plugins/video.php?href=${encodeURIComponent(
        canonicalUrl
      )}&show_text=false`,
      renderMode: 'iframe',
      aspectWidth: 16,
      aspectHeight: 9,
      allowedTypes: ['video', 'reel'],
    };
  }

  if (
    segments.includes('videos') &&
    segments.length >= 2 &&
    segments[segments.length - 1] !== 'videos'
  ) {
    const canonicalUrl = `https://www.facebook.com/${segments.join('/')}`;
    return {
      mediaType: 'video',
      provider: 'facebook',
      providerLabel: PROVIDER_LABELS.facebook,
      canonicalUrl,
      embedUrl: `https://www.facebook.com/plugins/video.php?href=${encodeURIComponent(
        canonicalUrl
      )}&show_text=false`,
      renderMode: 'iframe',
      aspectWidth: 16,
      aspectHeight: 9,
      allowedTypes: ['video', 'reel'],
    };
  }

  let canonicalPostUrl = '';
  if (cleanPath === '/permalink.php' || cleanPath === '/story.php') {
    const storyFbid = (parsed.searchParams.get('story_fbid') || '').trim();
    const pageId = (parsed.searchParams.get('id') || '').trim();
    if (
      storyFbid &&
      pageId &&
      ALNUM_SLUG_RE.test(storyFbid) &&
      ALNUM_SLUG_RE.test(pageId)
    ) {
      canonicalPostUrl = `https://www.facebook.com${cleanPath}?story_fbid=${encodeURIComponent(
        storyFbid
      )}&id=${encodeURIComponent(pageId)}`;
    }
  } else if (cleanPath === '/photo' || cleanPath === '/photo.php') {
    const fbid = (parsed.searchParams.get('fbid') || '').trim();
    if (fbid && ALNUM_SLUG_RE.test(fbid)) {
      canonicalPostUrl = `https://www.facebook.com/photo/?fbid=${encodeURIComponent(
        fbid
      )}`;
    }
  } else if (
    segments.length >= 3 &&
    (segments.includes('posts') ||
      (segments[0] === 'groups' && segments.includes('permalink')) ||
      segments.includes('photos'))
  ) {
    canonicalPostUrl = `https://www.facebook.com/${segments.join('/')}`;
  }

  if (canonicalPostUrl) {
    return {
      mediaType: 'post',
      provider: 'facebook',
      providerLabel: PROVIDER_LABELS.facebook,
      canonicalUrl: canonicalPostUrl,
      embedUrl: `https://www.facebook.com/plugins/post.php?href=${encodeURIComponent(
        canonicalPostUrl
      )}&show_text=true`,
      renderMode: 'iframe',
      allowedTypes: ['post', 'image', 'video'],
    };
  }

  return null;
}

function parseTikTokEmbed(parsed) {
  const host = parsed.hostname.toLowerCase();
  const segments = parsed.pathname.split('/').filter(Boolean);

  if (TIKTOK_SHORT_HOSTS.has(host)) {
    if (segments.length === 0 || !ALNUM_SLUG_RE.test(segments[0])) {
      return null;
    }
    return {
      mediaType: 'reel',
      provider: 'tiktok',
      providerLabel: PROVIDER_LABELS.tiktok,
      canonicalUrl: `https://${host}/${segments[0]}`,
      embedUrl: '',
      renderMode: 'card',
      allowedTypes: ['reel', 'video', 'post'],
    };
  }

  if (
    segments.length >= 2 &&
    segments[0] === 't' &&
    ALNUM_SLUG_RE.test(segments[1])
  ) {
    return {
      mediaType: 'reel',
      provider: 'tiktok',
      providerLabel: PROVIDER_LABELS.tiktok,
      canonicalUrl: `https://www.tiktok.com/t/${segments[1]}`,
      embedUrl: '',
      renderMode: 'card',
      allowedTypes: ['reel', 'video', 'post'],
    };
  }

  if (
    segments.length >= 3 &&
    segments[0].startsWith('@') &&
    segments[0].length > 1 &&
    (segments[1] === 'video' || segments[1] === 'photo') &&
    NUMERIC_ID_RE.test(segments[2])
  ) {
    const [user, kind, itemId] = segments;
    if (kind === 'video') {
      return {
        mediaType: 'reel',
        provider: 'tiktok',
        providerLabel: PROVIDER_LABELS.tiktok,
        canonicalUrl: `https://www.tiktok.com/${user}/video/${itemId}`,
        embedUrl: `https://www.tiktok.com/embed/v2/${itemId}`,
        renderMode: 'iframe',
        aspectWidth: 9,
        aspectHeight: 16,
        allowedTypes: ['reel', 'video'],
      };
    }
    return {
      mediaType: 'post',
      provider: 'tiktok',
      providerLabel: PROVIDER_LABELS.tiktok,
      canonicalUrl: `https://www.tiktok.com/${user}/photo/${itemId}`,
      embedUrl: '',
      renderMode: 'card',
      allowedTypes: ['post', 'image'],
    };
  }

  if (
    segments.length >= 2 &&
    (segments[0] === 'video' || segments[0] === 'embed') &&
    NUMERIC_ID_RE.test(segments[segments.length - 1])
  ) {
    const itemId = segments[segments.length - 1];
    return {
      mediaType: 'reel',
      provider: 'tiktok',
      providerLabel: PROVIDER_LABELS.tiktok,
      canonicalUrl: `https://www.tiktok.com/embed/v2/${itemId}`,
      embedUrl: `https://www.tiktok.com/embed/v2/${itemId}`,
      renderMode: 'iframe',
      aspectWidth: 9,
      aspectHeight: 16,
      allowedTypes: ['reel', 'video'],
    };
  }

  return null;
}

function parseXEmbed(parsed) {
  const segments = parsed.pathname.split('/').filter(Boolean);
  let canonicalUrl = '';

  if (
    segments.length >= 3 &&
    segments[1] === 'status' &&
    NUMERIC_ID_RE.test(segments[2])
  ) {
    canonicalUrl = `https://x.com/${segments[0]}/status/${segments[2]}`;
  } else if (
    segments.length >= 4 &&
    segments[0] === 'i' &&
    segments[1] === 'web' &&
    segments[2] === 'status' &&
    NUMERIC_ID_RE.test(segments[3])
  ) {
    canonicalUrl = `https://x.com/i/web/status/${segments[3]}`;
  }

  if (!canonicalUrl) return null;

  return {
    mediaType: 'post',
    provider: 'x',
    providerLabel: PROVIDER_LABELS.x,
    canonicalUrl,
    embedUrl: '',
    renderMode: 'card',
    allowedTypes: ['post', 'video', 'image'],
  };
}

function parseThreadsEmbed(parsed) {
  let segments = parsed.pathname.split('/').filter(Boolean);
  if (segments.length >= 4 && segments[segments.length - 1] === 'embed') {
    segments = segments.slice(0, -1);
  }

  const isPost =
    segments.length >= 3 &&
    segments[0].startsWith('@') &&
    segments[0].length > 1 &&
    segments[1] === 'post' &&
    ALNUM_SLUG_RE.test(segments[2]);
  if (isPost) {
    const canonicalUrl = `https://www.threads.net/${segments[0]}/post/${segments[2]}`;
    return {
      mediaType: 'post',
      provider: 'threads',
      providerLabel: PROVIDER_LABELS.threads,
      canonicalUrl,
      embedUrl: `${canonicalUrl}/embed`,
      renderMode: 'iframe',
      allowedTypes: ['post', 'video', 'reel', 'image'],
    };
  }

  if (
    segments.length >= 2 &&
    segments[0] === 't' &&
    ALNUM_SLUG_RE.test(segments[1])
  ) {
    return {
      mediaType: 'post',
      provider: 'threads',
      providerLabel: PROVIDER_LABELS.threads,
      canonicalUrl: `https://www.threads.net/t/${segments[1]}`,
      embedUrl: '',
      renderMode: 'card',
      allowedTypes: ['post', 'video', 'reel', 'image'],
    };
  }

  return null;
}

function parseLinkedInEmbed(parsed) {
  const segments = parsed.pathname.split('/').filter(Boolean);

  if (
    segments.length >= 4 &&
    segments[0] === 'embed' &&
    segments[1] === 'feed' &&
    segments[2] === 'update' &&
    segments[3].startsWith('urn:li:')
  ) {
    const urn = segments[3];
    return {
      mediaType: 'post',
      provider: 'linkedin',
      providerLabel: PROVIDER_LABELS.linkedin,
      canonicalUrl: `https://www.linkedin.com/feed/update/${urn}`,
      embedUrl: `https://www.linkedin.com/embed/feed/update/${urn}`,
      renderMode: 'iframe',
      allowedTypes: ['post', 'video', 'image'],
    };
  }

  if (
    segments.length >= 3 &&
    segments[0] === 'feed' &&
    segments[1] === 'update'
  ) {
    const urn = segments[2];
    const canonicalUrl = `https://www.linkedin.com/feed/update/${urn}`;
    if (urn.startsWith('urn:li:')) {
      return {
        mediaType: 'post',
        provider: 'linkedin',
        providerLabel: PROVIDER_LABELS.linkedin,
        canonicalUrl,
        embedUrl: `https://www.linkedin.com/embed/feed/update/${urn}`,
        renderMode: 'iframe',
        allowedTypes: ['post', 'video', 'image'],
      };
    }
    return {
      mediaType: 'post',
      provider: 'linkedin',
      providerLabel: PROVIDER_LABELS.linkedin,
      canonicalUrl,
      embedUrl: '',
      renderMode: 'card',
      allowedTypes: ['post', 'video', 'image'],
    };
  }

  if (
    segments.length >= 2 &&
    (segments[0] === 'posts' || segments[0] === 'pulse')
  ) {
    const canonicalUrl = `https://www.linkedin.com/${segments.join('/')}`;
    const activityMatch =
      segments[0] === 'posts' ? /activity-(\d+)/.exec(segments[1]) : null;
    if (activityMatch) {
      const urn = `urn:li:activity:${activityMatch[1]}`;
      return {
        mediaType: 'post',
        provider: 'linkedin',
        providerLabel: PROVIDER_LABELS.linkedin,
        canonicalUrl,
        embedUrl: `https://www.linkedin.com/embed/feed/update/${urn}`,
        renderMode: 'iframe',
        allowedTypes: ['post', 'video', 'image'],
      };
    }
    return {
      mediaType: 'post',
      provider: 'linkedin',
      providerLabel: PROVIDER_LABELS.linkedin,
      canonicalUrl,
      embedUrl: '',
      renderMode: 'card',
      allowedTypes: ['post', 'video', 'image'],
    };
  }

  return null;
}

function parseTelegramEmbed(parsed) {
  const segments = parsed.pathname.split('/').filter(Boolean);
  let canonicalUrl = '';

  if (
    segments.length >= 3 &&
    segments[0] === 's' &&
    HANDLE_RE.test(segments[1]) &&
    NUMERIC_ID_RE.test(segments[2])
  ) {
    canonicalUrl = `https://t.me/${segments[1]}/${segments[2]}`;
  } else if (
    segments.length >= 2 &&
    HANDLE_RE.test(segments[0]) &&
    NUMERIC_ID_RE.test(segments[1])
  ) {
    canonicalUrl = `https://t.me/${segments[0]}/${segments[1]}`;
  }

  if (!canonicalUrl) return null;

  return {
    mediaType: 'post',
    provider: 'telegram',
    providerLabel: PROVIDER_LABELS.telegram,
    canonicalUrl,
    embedUrl: `${canonicalUrl}?embed=1`,
    renderMode: 'iframe',
    allowedTypes: ['post', 'video', 'image', 'audio'],
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
    providerLabel: PROVIDER_LABELS.soundcloud,
    canonicalUrl,
    embedUrl,
    renderMode: 'iframe',
    allowedTypes: ['audio'],
  };
}

function parseSpotifyEmbed(parsed) {
  let segments = parsed.pathname.split('/').filter(Boolean);
  if (segments.length > 0 && segments[0].startsWith('intl-')) {
    segments = segments.slice(1);
  }
  if (segments.length > 0 && segments[0] === 'embed') {
    segments = segments.slice(1);
  }

  if (
    segments.length < 2 ||
    !['track', 'episode', 'show', 'playlist', 'album'].includes(segments[0]) ||
    !SPOTIFY_ID_RE.test(segments[1])
  ) {
    return null;
  }

  const [kind, itemId] = segments;
  return {
    mediaType: 'audio',
    provider: 'spotify',
    providerLabel: PROVIDER_LABELS.spotify,
    canonicalUrl: `https://open.spotify.com/${kind}/${itemId}`,
    embedUrl: `https://open.spotify.com/embed/${kind}/${itemId}`,
    renderMode: 'iframe',
    allowedTypes: ['audio'],
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
    providerLabel: PROVIDER_LABELS.google_drive,
    canonicalUrl: `https://drive.google.com/file/d/${fileId}/view`,
    embedUrl: `https://drive.google.com/file/d/${fileId}/preview`,
    renderMode: 'iframe',
    allowedTypes: ['audio', 'video', 'image', 'post'],
  };
}

function parseGooglePhotosEmbed(parsed) {
  const host = parsed.hostname.toLowerCase();
  const segments = parsed.pathname.split('/').filter(Boolean);
  if (segments.length === 0) return null;

  let canonicalUrl = '';
  if (host === 'photos.app.goo.gl') {
    canonicalUrl = `https://photos.app.goo.gl/${segments[0]}`;
  } else if (
    ['share', 'photo', 'album'].includes(segments[0]) ||
    (segments.length >= 3 &&
      segments[0] === 'u' &&
      ['share', 'photo', 'album'].includes(segments[2]))
  ) {
    canonicalUrl = `https://photos.google.com/${segments.join('/')}${parsed.search || ''}`;
  } else {
    return null;
  }

  return {
    mediaType: 'image',
    provider: 'google_photos',
    providerLabel: PROVIDER_LABELS.google_photos,
    canonicalUrl,
    embedUrl: '',
    renderMode: 'card',
    allowedTypes: ['image', 'post', 'video'],
  };
}

function parseCanvaEmbed(parsed) {
  const segments = parsed.pathname.split('/').filter(Boolean);
  if (
    segments.length < 2 ||
    segments[0] !== 'design' ||
    !CANVA_ID_RE.test(segments[1])
  ) {
    return null;
  }

  const designId = segments[1];
  return {
    mediaType: 'post',
    provider: 'canva',
    providerLabel: PROVIDER_LABELS.canva,
    canonicalUrl: `https://www.canva.com/design/${designId}/view`,
    embedUrl: `https://www.canva.com/design/${designId}/view?embed`,
    renderMode: 'iframe',
    allowedTypes: ['post', 'image', 'video'],
  };
}

function parseExternalImageUrl(parsed, cleaned) {
  const host = parsed.hostname.toLowerCase();
  if (!isPublicHostname(host)) return null;
  if (isDisallowedAssetExtension(parsed.pathname)) return null;
  return {
    mediaType: 'image',
    provider: 'external_image',
    providerLabel: PROVIDER_LABELS.external_image,
    canonicalUrl: cleaned,
    embedUrl: '',
    renderMode: 'image',
    allowedTypes: ['image'],
  };
}

/**
 * Resolve and normalize an external media URL (video, reel, post, image, or audio).
 * Returns null for untrusted domains, non-HTTPS URLs, raw A/V files, credentials, or type mismatches.
 */
export function resolveExternalMediaEmbed(input, explicitMediaType = null) {
  if (!input) return null;

  let rawUrl = '';
  let requestedType = explicitMediaType;
  let title = '';
  let explicitAspectWidth = null;
  let explicitAspectHeight = null;

  const parseDim = (val) => {
    if (typeof val !== 'number' || !Number.isFinite(val)) return null;
    const rounded = Math.round(val);
    return rounded >= 1 && rounded <= 10000 ? rounded : null;
  };

  if (typeof input === 'string') {
    rawUrl = input;
  } else if (typeof input === 'object') {
    rawUrl =
      input.url ||
      input.canonicalUrl ||
      input.canonical_url ||
      input.embedUrl ||
      input.embed_url ||
      input.originalUrl ||
      input.original_url ||
      '';
    if (requestedType == null) {
      requestedType = input.mediaType ?? input.media_type ?? null;
    }
    title = typeof input.title === 'string' ? input.title.trim() : '';
    explicitAspectWidth = parseDim(input.aspectWidth ?? input.aspect_width);
    explicitAspectHeight = parseDim(input.aspectHeight ?? input.aspect_height);
  } else {
    return null;
  }

  if (typeof rawUrl !== 'string') return null;
  const cleaned = rawUrl.trim();
  if (!cleaned || UNSAFE_MEDIA_URL_CHARS_RE.test(cleaned)) return null;

  let normalizedRequested = null;
  if (requestedType != null && String(requestedType).trim()) {
    normalizedRequested = String(requestedType).trim().toLowerCase();
    if (!ALLOWED_EXTERNAL_MEDIA_TYPES.includes(normalizedRequested)) {
      return null;
    }
  }

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
  if (hasTraversalSegments(parsed.pathname)) {
    return null;
  }

  const host = parsed.hostname.toLowerCase();
  let resolved = null;

  if (YOUTUBE_HOSTS.has(host)) {
    resolved = parseYouTubeEmbed(parsed);
  } else if (VIMEO_HOSTS.has(host)) {
    resolved = parseVimeoEmbed(parsed);
  } else if (DAILYMOTION_HOSTS.has(host)) {
    resolved = parseDailymotionEmbed(parsed);
  } else if (INSTAGRAM_HOSTS.has(host)) {
    resolved = parseInstagramEmbed(parsed);
  } else if (FACEBOOK_HOSTS.has(host)) {
    resolved = parseFacebookEmbed(parsed);
  } else if (TIKTOK_HOSTS.has(host)) {
    resolved = parseTikTokEmbed(parsed);
  } else if (X_HOSTS.has(host)) {
    resolved = parseXEmbed(parsed);
  } else if (THREADS_HOSTS.has(host)) {
    resolved = parseThreadsEmbed(parsed);
  } else if (LINKEDIN_HOSTS.has(host)) {
    resolved = parseLinkedInEmbed(parsed);
  } else if (TELEGRAM_HOSTS.has(host)) {
    resolved = parseTelegramEmbed(parsed);
  } else if (SOUNDCLOUD_HOSTS.has(host)) {
    resolved = parseSoundCloudEmbed(parsed);
  } else if (SPOTIFY_HOSTS.has(host)) {
    resolved = parseSpotifyEmbed(parsed);
  } else if (GOOGLE_DRIVE_HOSTS.has(host)) {
    resolved = parseGoogleDriveEmbed(parsed);
  } else if (GOOGLE_PHOTOS_HOSTS.has(host)) {
    resolved = parseGooglePhotosEmbed(parsed);
  } else if (CANVA_HOSTS.has(host)) {
    resolved = parseCanvaEmbed(parsed);
  } else {
    const ext = getPathExtension(parsed.pathname);
    if (
      !isDisallowedAssetExtension(parsed.pathname) &&
      (EXTERNAL_IMAGE_EXTENSIONS.has(ext) || normalizedRequested === 'image')
    ) {
      resolved = parseExternalImageUrl(parsed, cleaned);
    }
  }

  if (!resolved) {
    return null;
  }

  const allowedTypes = resolved.allowedTypes || [resolved.mediaType];
  let finalMediaType = resolved.mediaType;
  if (normalizedRequested !== null) {
    if (!allowedTypes.includes(normalizedRequested)) {
      return null;
    }
    finalMediaType = normalizedRequested;
  }

  const { allowedTypes: _ignoredAllowed, ...publicResolved } = resolved;

  let aspectWidth = publicResolved.aspectWidth ?? null;
  let aspectHeight = publicResolved.aspectHeight ?? null;
  const hasExplicitDims =
    explicitAspectWidth !== null && explicitAspectHeight !== null;
  if (hasExplicitDims) {
    aspectWidth = explicitAspectWidth;
    aspectHeight = explicitAspectHeight;
  } else if (
    finalMediaType === 'reel' &&
    (!aspectWidth || !aspectHeight || aspectWidth > aspectHeight)
  ) {
    aspectWidth = 9;
    aspectHeight = 16;
  }

  const output = {
    ...publicResolved,
    mediaType: finalMediaType,
    title,
    hostedExternally: true,
  };
  if (aspectWidth && aspectHeight) {
    output.aspectWidth = aspectWidth;
    output.aspectHeight = aspectHeight;
  }
  return output;
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
  const seenEmbedKeys = new Set();

  const addEmbedCandidate = (candidate, explicitType = null) => {
    const resolved = resolveExternalMediaEmbed(candidate, explicitType);
    if (!resolved) return;
    const dedupeKey = resolved.embedUrl || resolved.canonicalUrl;
    if (!dedupeKey || seenEmbedKeys.has(dedupeKey)) {
      return;
    }
    seenEmbedKeys.add(dedupeKey);
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
