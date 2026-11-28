import { API_BASE_URL, resolveMediaUrl } from './apiConfig.js';
import { extractPostMedia, sanitizeImageUrl } from './mediaEmbeds.js';
import { buildPostDeepLink, sanitizeShareText } from './whatsappShare.js';

export const DEFAULT_SITE_META = {
  title: 'لجنة أولياء أمور الطلاب - مدرسة المحجر الابتدائية',
  description:
    'المنصة الرقمية للتواصل المجتمعي – لجنة أولياء أمور الطلاب في مدرسة المحجر الابتدائية: الإعلانات، الفعاليات، والنماذج التفاعلية للأهالي.',
  ogDescription:
    'تابعوا أحدث إعلانات وفعاليات مدرسة المحجر الابتدائية، وشاركوا آراءكم وسجّلوا في الأنشطة المدرسية بسهولة.',
  type: 'website',
  image: '/logo.jpg',
  twitterCard: 'summary',
};

function truncateMetaDescription(text, maxLength = 200) {
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

function resolvePostMetaImage(post, { apiBaseUrl = API_BASE_URL } = {}) {
  const rawPrimary = sanitizeImageUrl(post?.imageUrl ?? post?.image_url ?? '');
  if (rawPrimary) {
    return {
      image: resolveMediaUrl(rawPrimary, apiBaseUrl),
      hasCustomImage: true,
    };
  }

  const { images, embeds } = extractPostMedia(post);
  if (images.length > 0 && images[0]?.url) {
    return {
      image: resolveMediaUrl(images[0].url, apiBaseUrl),
      hasCustomImage: true,
    };
  }

  for (const embed of embeds) {
    if (embed?.provider === 'youtube' && typeof embed.embedUrl === 'string') {
      const match = embed.embedUrl.match(/\/embed\/([A-Za-z0-9_-]{11})(?:[/?#]|$)/);
      if (match) {
        return {
          image: `https://i.ytimg.com/vi/${match[1]}/hqdefault.jpg`,
          hasCustomImage: true,
        };
      }
    }
  }

  return {
    image: DEFAULT_SITE_META.image,
    hasCustomImage: false,
  };
}

export function buildPostDocumentMeta(post, { baseUrl, apiBaseUrl = API_BASE_URL } = {}) {
  if (!post || typeof post !== 'object' || Array.isArray(post)) {
    return {
      title: DEFAULT_SITE_META.title,
      ogTitle: DEFAULT_SITE_META.title,
      description: DEFAULT_SITE_META.description,
      ogDescription: DEFAULT_SITE_META.ogDescription,
      type: DEFAULT_SITE_META.type,
      url: baseUrl || '',
      image: DEFAULT_SITE_META.image,
      twitterCard: DEFAULT_SITE_META.twitterCard,
    };
  }

  const postTitle = sanitizeShareText(post.title) || DEFAULT_SITE_META.title;
  const fullTitle =
    postTitle === DEFAULT_SITE_META.title
      ? DEFAULT_SITE_META.title
      : `${postTitle} | ${DEFAULT_SITE_META.title}`;
  const rawBody =
    sanitizeShareText(post.summary ?? post.description ?? post.content ?? '', {
      allowNewlines: false,
    }) || '';
  const description =
    truncateMetaDescription(rawBody) || DEFAULT_SITE_META.description;
  const url = buildPostDeepLink(post, { baseUrl });
  const { image, hasCustomImage } = resolvePostMetaImage(post, { apiBaseUrl });

  return {
    title: fullTitle,
    ogTitle: postTitle,
    description,
    ogDescription: description,
    type: 'article',
    url,
    image,
    twitterCard: hasCustomImage ? 'summary_large_image' : 'summary',
  };
}

function setMetaTag(doc, attrName, attrValue, content) {
  if (!doc || typeof doc.querySelector !== 'function') return;
  let tag = doc.querySelector(`meta[${attrName}="${attrValue}"]`);
  if (!tag && doc.head && typeof doc.createElement === 'function') {
    tag = doc.createElement('meta');
    tag.setAttribute(attrName, attrValue);
    doc.head.appendChild(tag);
  }
  if (tag && typeof tag.setAttribute === 'function') {
    tag.setAttribute('content', content);
  }
}

export function applyDocumentMetaForPost(
  post,
  {
    doc = typeof document !== 'undefined' ? document : null,
    baseUrl,
    apiBaseUrl = API_BASE_URL,
  } = {}
) {
  if (!doc) return;
  const meta = buildPostDocumentMeta(post, { baseUrl, apiBaseUrl });
  doc.title = meta.title;

  setMetaTag(doc, 'name', 'description', meta.description);
  setMetaTag(doc, 'property', 'og:type', meta.type);
  setMetaTag(doc, 'property', 'og:title', meta.ogTitle);
  setMetaTag(doc, 'property', 'og:description', meta.ogDescription);
  if (meta.url) {
    setMetaTag(doc, 'property', 'og:url', meta.url);
  }
  setMetaTag(doc, 'property', 'og:image', meta.image);
  setMetaTag(doc, 'name', 'twitter:card', meta.twitterCard);
  setMetaTag(doc, 'name', 'twitter:title', meta.ogTitle);
  setMetaTag(doc, 'name', 'twitter:description', meta.description);
  setMetaTag(doc, 'name', 'twitter:image', meta.image);
}
