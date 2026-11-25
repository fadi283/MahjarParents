import { CATEGORY_LABELS } from '../components/AnnouncementCard.jsx';
import {
  ALLOWED_EXTERNAL_MEDIA_TYPES,
  resolveExternalMediaEmbed,
  sanitizeImageUrl,
} from './mediaEmbeds.js';

export const ADMIN_POST_CATEGORY_OPTIONS = [
  { id: 'general', label: CATEGORY_LABELS.general },
  { id: 'upcoming_event', label: CATEGORY_LABELS.upcoming_event },
  { id: 'student_activity', label: CATEGORY_LABELS.student_activity },
  { id: 'updates', label: CATEGORY_LABELS.updates },
];

export const FORM_TYPE_LABELS = {
  feedback: 'نموذج إبداء الرأي والمقترحات',
  help_request: 'نموذج طرح مشكلة أو طلب مساعدة',
  event_registration: 'استمارة التسجيل في فعالية',
};

export const FORM_TYPE_OPTIONS = [
  { id: 'feedback', label: FORM_TYPE_LABELS.feedback },
  { id: 'help_request', label: FORM_TYPE_LABELS.help_request },
  { id: 'event_registration', label: FORM_TYPE_LABELS.event_registration },
];

const BIDI_OVERRIDE_RE = /[\u202a-\u202e\u2066-\u2069]/g;
const CONTROL_CHARS_NO_NL_RE = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g;
const CONTROL_CHARS_ALL_RE = /[\x00-\x1f\x7f]/g;
const DANGEROUS_BLOCK_RE =
  /<\s*(script|style|iframe|object|embed|svg)\b[^>]*>[\s\S]*?<\s*\/\s*\1\s*>/gi;
const HTML_TAG_RE = /<\s*\/?[a-zA-Z!][^<>]*>/g;
const UNCLOSED_TAG_RE = /<\s*\/?[a-zA-Z!][^\s<>]*/g;
const DANGEROUS_SCHEME_RE = /(?:javascript|vbscript|data\s*:\s*text\/html)\s*:/gi;
const UNSAFE_URL_CHARS_RE = /[\s\x00-\x1f\x7f<>"']/;
const EMAIL_RE = /^[^@\s<>"']+@[^@\s<>"']+\.[^@\s<>"']+$/;
const PHONE_RE = /^[0-9+\-\s()]{5,25}$/;
const EVENT_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const GOOGLE_FORMS_PATH_RE =
  /^\/forms(?:\/u\/\d+)?\/d\/(?:(e)\/)?([A-Za-z0-9_-]{10,})(?:\/viewform)?\/?$/;
const GOOGLE_FORMS_SHORT_PATH_RE = /^\/([A-Za-z0-9_-]{6,64})\/?$/;
const GOOGLE_FORMS_ENTRY_PARAM_RE = /^entry\.\d+$/;

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

/**
 * Sanitize plain text against XSS/HTML/control-char injection matching backend cms_security.py.
 */
export function sanitizeAdminText(value, { allowNewlines = false } = {}) {
  if (typeof value !== 'string') return '';

  let normalized = value.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  normalized = normalized.replace(BIDI_OVERRIDE_RE, '');
  normalized = allowNewlines
    ? normalized.replace(CONTROL_CHARS_NO_NL_RE, '')
    : normalized.replace(CONTROL_CHARS_ALL_RE, ' ');

  let cleaned = normalized;
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
    return cleaned
      .split('\n')
      .map((line) => line.trim().replace(/\s+/g, ' '))
      .filter(Boolean)
      .join('\n');
  }

  return cleaned.trim().replace(/\s+/g, ' ');
}

function parsePositiveIntOrNull(rawValue) {
  if (rawValue === null || rawValue === undefined) {
    return { valid: true, value: null };
  }
  if (typeof rawValue === 'boolean') {
    return { valid: false, value: null };
  }
  if (typeof rawValue === 'number') {
    if (Number.isInteger(rawValue) && rawValue >= 1) {
      return { valid: true, value: rawValue };
    }
    return { valid: false, value: null };
  }
  if (typeof rawValue === 'string') {
    const trimmed = rawValue.trim();
    if (!trimmed) {
      return { valid: true, value: null };
    }
    if (!/^\d+$/.test(trimmed)) {
      return { valid: false, value: null };
    }
    const parsed = Number.parseInt(trimmed, 10);
    if (parsed >= 1) {
      return { valid: true, value: parsed };
    }
    return { valid: false, value: null };
  }
  return { valid: false, value: null };
}

function isValidCalendarDate(dateStr) {
  if (!EVENT_DATE_RE.test(dateStr)) return false;
  const [year, month, day] = dateStr.split('-').map((n) => Number.parseInt(n, 10));
  const dt = new Date(Date.UTC(year, month - 1, day));
  return (
    dt.getUTCFullYear() === year &&
    dt.getUTCMonth() === month - 1 &&
    dt.getUTCDate() === day
  );
}

/**
 * Strictly validate and normalize a Google Forms URL restricted to docs.google.com/forms or forms.gle.
 */
export function validateGoogleFormUrl(rawUrl) {
  if (typeof rawUrl !== 'string' || !rawUrl.trim()) {
    return { valid: false, error: 'يرجى إدخال رابط نموذج Google Forms.' };
  }

  const cleaned = rawUrl.trim();
  if (UNSAFE_URL_CHARS_RE.test(cleaned)) {
    return { valid: false, error: 'رابط النموذج يحتوي على محارف غير صالحة.' };
  }

  const rawPath = cleaned
    .replace(/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\/[^/?#]*/, '')
    .split(/[?#]/)[0];
  if (hasTraversalSegments(rawPath)) {
    return { valid: false, error: 'مسار الرابط يحتوي على مقاطع غير آمنة.' };
  }

  let parsed;
  try {
    parsed = new URL(cleaned);
  } catch {
    return { valid: false, error: 'صيغة رابط نموذج Google Forms غير صالحة.' };
  }

  if (parsed.protocol.toLowerCase() !== 'https:') {
    return { valid: false, error: 'يجب أن يبدأ رابط Google Forms ببروتوكول https://.' };
  }

  if (parsed.username || parsed.password) {
    return { valid: false, error: 'لا يُسمح بتضمين بيانات اعتماد داخل الرابط.' };
  }

  if (parsed.port) {
    return { valid: false, error: 'لا يُسمح بتحديد منفذ مخصص في رابط Google Forms.' };
  }

  const host = parsed.hostname.toLowerCase();
  if (host !== 'docs.google.com' && host !== 'forms.gle') {
    return {
      valid: false,
      error: 'يجب أن يكون الرابط من نطاق Google Forms المعتمد (docs.google.com أو forms.gle).',
    };
  }

  if (hasTraversalSegments(parsed.path ?? parsed.pathname)) {
    return { valid: false, error: 'مسار الرابط يحتوي على مقاطع غير آمنة.' };
  }

  if (host === 'forms.gle') {
    const shortMatch = GOOGLE_FORMS_SHORT_PATH_RE.exec(parsed.pathname);
    if (!shortMatch) {
      return {
        valid: false,
        error: 'الرابط المختصر لا يطابق صيغة forms.gle صالحة.',
      };
    }
    const shortCode = shortMatch[1];
    const canonicalShort = `https://forms.gle/${shortCode}`;
    return {
      valid: true,
      canonicalUrl: canonicalShort,
      embedUrl: canonicalShort,
      provider: 'google_forms',
      formId: shortCode,
    };
  }

  const match = GOOGLE_FORMS_PATH_RE.exec(parsed.pathname);
  if (!match) {
    return {
      valid: false,
      error: 'الرابط لا يطابق مسار نموذج Google Forms صالحاً (/forms/d/...).',
    };
  }

  const isPublishedE = match[1] === 'e';
  const formId = match[2];
  const basePath = isPublishedE
    ? `/forms/d/e/${formId}/viewform`
    : `/forms/d/${formId}/viewform`;

  const safeEntries = [];
  for (const [key, val] of parsed.searchParams.entries()) {
    if (GOOGLE_FORMS_ENTRY_PARAM_RE.test(key)) {
      const safeVal = sanitizeAdminText(val).slice(0, 200);
      if (safeVal) {
        safeEntries.push([key, safeVal]);
      }
    }
  }

  const canonicalBase = `https://docs.google.com${basePath}`;
  if (safeEntries.length > 0) {
    const query = safeEntries
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join('&');
    return {
      valid: true,
      canonicalUrl: `${canonicalBase}?${query}`,
      embedUrl: `${canonicalBase}?embedded=true&${query}`,
      provider: 'google_forms',
      formId,
    };
  }

  return {
    valid: true,
    canonicalUrl: canonicalBase,
    embedUrl: `${canonicalBase}?embedded=true`,
    provider: 'google_forms',
    formId,
  };
}

export function validateCommitteeInput(input = {}) {
  const errors = {};
  const fullName = sanitizeAdminText(input.fullName ?? '');
  const role = sanitizeAdminText(input.role ?? '');
  const responsibilitySummary = sanitizeAdminText(input.responsibilitySummary ?? '');
  const rawEmail = typeof input.email === 'string' ? input.email.trim() : '';
  const rawPhone =
    typeof input.phone === 'string' ? input.phone.trim().replace(/\s+/g, ' ') : '';
  const rawAvatar = typeof input.avatarUrl === 'string' ? input.avatarUrl.trim() : '';

  if (fullName.length < 2 || fullName.length > 120) {
    errors.fullName = 'الاسم الكامل مطلوب ويجب أن يتراوح بين حرفين و120 حرفاً.';
  }
  if (role.length < 2 || role.length > 120) {
    errors.role = 'الدور أو الصفة الوظيفية مطلوبة (2 إلى 120 حرفاً).';
  }
  if (responsibilitySummary.length > 500) {
    errors.responsibilitySummary = 'نبذة المهام يجب ألا تتجاوز 500 حرف.';
  }
  if (rawEmail) {
    if (rawEmail.length > 254 || UNSAFE_URL_CHARS_RE.test(rawEmail) || !EMAIL_RE.test(rawEmail)) {
      errors.email = 'صيغة البريد الإلكتروني غير صالحة.';
    }
  }
  if (rawPhone && !PHONE_RE.test(rawPhone)) {
    errors.phone = 'صيغة رقم الهاتف غير صالحة (أرقام ورموز + - فقط).';
  }

  let avatarUrl = '';
  if (rawAvatar) {
    const safeAvatar = sanitizeImageUrl(rawAvatar);
    if (!safeAvatar) {
      errors.avatarUrl =
        'رابط الصورة غير صالح (يجب استخدام HTTPS أو مسار آمن دون ملفات SVG أو وسائط).';
    } else {
      avatarUrl = safeAvatar;
    }
  }

  const hasDisplayOrder =
    Object.prototype.hasOwnProperty.call(input, 'displayOrder') &&
    input.displayOrder !== undefined;
  const orderCheck = hasDisplayOrder
    ? parsePositiveIntOrNull(input.displayOrder)
    : { valid: true, value: undefined };
  if (!orderCheck.valid) {
    errors.displayOrder = 'ترتيب العرض يجب أن يكون رقماً صحيحاً موجباً (1 فأكثر).';
  }

  const payload = {
    fullName,
    role,
    responsibilitySummary,
    email: rawEmail,
    phone: rawPhone,
    avatarUrl,
    isDirectContact: input.isDirectContact === true,
  };
  if (hasDisplayOrder) {
    payload.displayOrder = orderCheck.value;
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
    payload,
  };
}

export function validatePostInput(input = {}) {
  const errors = {};
  const title = sanitizeAdminText(input.title ?? '');
  const summary = sanitizeAdminText(input.summary ?? '', { allowNewlines: true });
  const category = typeof input.category === 'string' ? input.category.trim() : 'general';
  const rawEventDate = typeof input.eventDate === 'string' ? input.eventDate.trim() : '';
  const rawImage = typeof input.imageUrl === 'string' ? input.imageUrl.trim() : '';

  if (title.length < 2 || title.length > 200) {
    errors.title = 'عنوان الإعلان مطلوب (2 إلى 200 حرف).';
  }
  if (!summary || summary.length > 1000) {
    errors.summary = 'نص الإعلان مطلوب ويجب ألا يتجاوز 1000 حرف.';
  }
  if (!ADMIN_POST_CATEGORY_OPTIONS.some((opt) => opt.id === category)) {
    errors.category = 'التصنيف المختار غير صالح.';
  }
  if (rawEventDate && !isValidCalendarDate(rawEventDate)) {
    errors.eventDate = 'تاريخ الفعالية يجب أن يكون بصيغة YYYY-MM-DD وتاريخاً صحيحاً.';
  }

  let imageUrl = '';
  if (rawImage) {
    const safeImage = sanitizeImageUrl(rawImage);
    if (!safeImage) {
      errors.imageUrl =
        'رابط الصورة غير صالح (يجب استخدام HTTPS أو مسار آمن دون ملفات SVG أو وسائط).';
    } else {
      imageUrl = safeImage;
    }
  }

  const candidateUrls = [];
  if (Array.isArray(input.mediaLinks)) {
    for (const item of input.mediaLinks) {
      if (typeof item === 'string') {
        const cleaned = item.trim();
        if (cleaned) candidateUrls.push(cleaned);
      } else if (item && typeof item === 'object') {
        const cleaned = String(
          item.url ||
            item.canonicalUrl ||
            item.canonical_url ||
            item.originalUrl ||
            item.original_url ||
            item.embedUrl ||
            item.embed_url ||
            ''
        ).trim();
        if (cleaned) candidateUrls.push(cleaned);
      }
    }
  } else if (typeof input.mediaLinks === 'string') {
    const cleaned = input.mediaLinks.trim();
    if (cleaned) candidateUrls.push(cleaned);
  }

  const mediaLinks = [];
  const seenUrls = new Set();
  for (const url of candidateUrls) {
    if (!seenUrls.has(url)) {
      seenUrls.add(url);
      mediaLinks.push(url);
    }
  }

  for (const url of mediaLinks) {
    if (!resolveExternalMediaEmbed(url)) {
      errors.mediaLinks =
        'أحد روابط الوسائط غير صالح أو من نطاق غير معتمد. يرجى استخدام رابط HTTPS من المنصات المعتمدة (YouTube، Vimeo، Dailymotion، Instagram، Facebook، TikTok، X، Threads، LinkedIn، Telegram، SoundCloud، Spotify، Google Drive، Google Photos، Canva) أو رابط صورة خارجية آمنة.';
      break;
    }
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
    payload: {
      title,
      summary,
      category,
      eventDate: rawEventDate,
      imageUrl,
      mediaLinks,
    },
  };
}

export function validateMediaLinkInput(input = {}) {
  const errors = {};
  const rawUrl = typeof input.url === 'string' ? input.url.trim() : '';
  const rawType = typeof input.mediaType === 'string' ? input.mediaType.trim().toLowerCase() : '';
  const title = sanitizeAdminText(input.title ?? '');

  if (title.length > 160) {
    errors.title = 'عنوان الرابط يجب ألا يتجاوز 160 حرفاً.';
  }

  if (rawType && !ALLOWED_EXTERNAL_MEDIA_TYPES.includes(rawType)) {
    errors.mediaType =
      'نوع الوسائط يجب أن يكون فيديو أو رييل أو منشور أو صورة أو صوت.';
  }

  const resolved = rawUrl ? resolveExternalMediaEmbed(rawUrl, rawType || null) : null;
  if (!rawUrl || !resolved) {
    errors.url =
      'يرجى إدخال رابط HTTPS صالح من المنصات المعتمدة (YouTube، Vimeo، Dailymotion، Instagram، Facebook، TikTok، X، Threads، LinkedIn، Telegram، SoundCloud، Spotify، Google Drive، Google Photos، Canva) أو رابط صورة خارجية آمنة متوافق مع النوع المحدد.';
  }

  const postCheck = parsePositiveIntOrNull(input.postId);
  if (!postCheck.valid) {
    errors.postId = 'معرّف الإعلان المرتبط غير صالح.';
  }

  const payload = {
    url: rawUrl,
    title,
    postId: postCheck.value,
  };
  if (rawType) {
    payload.mediaType = rawType;
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
    payload,
    resolved,
  };
}

export function validateGoogleFormInput(input = {}) {
  const errors = {};
  const formType = typeof input.formType === 'string' ? input.formType.trim() : '';
  const title = sanitizeAdminText(input.title ?? '');
  const description = sanitizeAdminText(input.description ?? '', { allowNewlines: true });

  if (!FORM_TYPE_OPTIONS.some((opt) => opt.id === formType)) {
    errors.formType = 'نوع النموذج غير صالح.';
  }
  if (title.length < 2 || title.length > 200) {
    errors.title = 'عنوان النموذج مطلوب (2 إلى 200 حرف).';
  }
  if (description.length > 500) {
    errors.description = 'وصف النموذج يجب ألا يتجاوز 500 حرف.';
  }

  const urlCheck = validateGoogleFormUrl(input.embedUrl ?? '');
  if (!urlCheck.valid) {
    errors.embedUrl = urlCheck.error;
  }

  if (typeof input.active !== 'boolean') {
    errors.active = 'حالة التفعيل يجب أن تكون قيمة منطقية صحيحة.';
  }

  const hasDisplayOrder =
    Object.prototype.hasOwnProperty.call(input, 'displayOrder') &&
    input.displayOrder !== undefined;
  const orderCheck = hasDisplayOrder
    ? parsePositiveIntOrNull(input.displayOrder)
    : { valid: true, value: undefined };
  if (!orderCheck.valid) {
    errors.displayOrder = 'ترتيب العرض يجب أن يكون رقماً صحيحاً موجباً (1 فأكثر).';
  }

  const payload = {
    formType,
    title,
    description,
    embedUrl: urlCheck.valid ? urlCheck.embedUrl : '',
    active: input.active,
  };
  if (hasDisplayOrder) {
    payload.displayOrder = orderCheck.value;
  }

  return {
    valid: Object.keys(errors).length === 0,
    errors,
    payload,
  };
}
