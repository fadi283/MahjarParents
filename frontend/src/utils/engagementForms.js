import { sanitizeAdminText, validateGoogleFormUrl } from './adminValidation.js';

export const ENGAGEMENT_FORM_META = {
  feedback: {
    label: 'إبداء الرأي والمقترحات',
    badge: 'مقترحات وآراء',
  },
  help_request: {
    label: 'طلب مساعدة أو طرح مشكلة',
    badge: 'مساعدة وبلاغات',
  },
  event_registration: {
    label: 'التسجيل في فعالية',
    badge: 'تسجيل فعاليات',
  },
};

export const ENGAGEMENT_FORM_TYPES = [
  { id: 'all', label: 'الكل' },
  { id: 'feedback', label: ENGAGEMENT_FORM_META.feedback.label },
  { id: 'help_request', label: ENGAGEMENT_FORM_META.help_request.label },
  {
    id: 'event_registration',
    label: ENGAGEMENT_FORM_META.event_registration.label,
  },
];

export const FORM_TYPE_PRIORITY = {
  feedback: 1,
  help_request: 2,
  event_registration: 3,
};

/**
 * Validate, sanitize, and normalize a single Google Form configuration record.
 * Returns null for inactive, untrusted, malformed, or XSS-only records.
 */
export function normalizeEngagementForm(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return null;
  }

  if (Object.prototype.hasOwnProperty.call(raw, 'active') && raw.active !== true) {
    return null;
  }

  const rawType = raw.formType ?? raw.form_type;
  const formType = typeof rawType === 'string' ? rawType.trim() : '';
  if (!Object.prototype.hasOwnProperty.call(FORM_TYPE_PRIORITY, formType)) {
    return null;
  }

  const rawUrl =
    raw.embedUrl ??
    raw.embed_url ??
    raw.canonicalUrl ??
    raw.canonical_url ??
    raw.directUrl ??
    raw.direct_url ??
    raw.url ??
    '';

  const urlCheck = validateGoogleFormUrl(rawUrl);
  if (!urlCheck.valid) {
    return null;
  }

  const title = sanitizeAdminText(raw.title ?? '');
  if (!title || title.length > 200) {
    return null;
  }

  const description = sanitizeAdminText(raw.description ?? '', {
    allowNewlines: true,
  }).slice(0, 500);

  const rawOrder = raw.displayOrder ?? raw.display_order;
  const displayOrder =
    typeof rawOrder === 'number' && Number.isInteger(rawOrder) && rawOrder >= 1
      ? rawOrder
      : null;

  const id = raw.id ?? urlCheck.formId;

  return {
    id,
    formType,
    title,
    description,
    embedUrl: urlCheck.embedUrl,
    canonicalUrl: urlCheck.canonicalUrl,
    directUrl: urlCheck.canonicalUrl,
    provider: urlCheck.provider,
    formId: urlCheck.formId,
    active: true,
    displayOrder,
  };
}

/**
 * Normalize, deduplicate, sort deterministically, and optionally filter active engagement forms.
 */
export function normalizeAndFilterEngagementForms(
  forms = [],
  selectedType = 'all'
) {
  if (!Array.isArray(forms)) return [];

  const seenIds = new Set();
  const normalized = [];

  for (const raw of forms) {
    const form = normalizeEngagementForm(raw);
    if (!form) continue;
    const dedupKey = String(form.id);
    if (seenIds.has(dedupKey)) continue;
    seenIds.add(dedupKey);
    normalized.push(form);
  }

  normalized.sort((a, b) => {
    const hasOrderA = a.displayOrder !== null ? 0 : 1;
    const hasOrderB = b.displayOrder !== null ? 0 : 1;
    if (hasOrderA !== hasOrderB) {
      return hasOrderA - hasOrderB;
    }

    const orderA = a.displayOrder ?? 9999;
    const orderB = b.displayOrder ?? 9999;
    if (orderA !== orderB) {
      return orderA - orderB;
    }

    const priorityA = FORM_TYPE_PRIORITY[a.formType] ?? 99;
    const priorityB = FORM_TYPE_PRIORITY[b.formType] ?? 99;
    if (priorityA !== priorityB) {
      return priorityA - priorityB;
    }

    const numA = Number(a.id);
    const numB = Number(b.id);
    const validNumA = Number.isFinite(numA) ? numA : 0;
    const validNumB = Number.isFinite(numB) ? numB : 0;
    return validNumA - validNumB;
  });

  const normalizedType =
    typeof selectedType === 'string' && selectedType.trim()
      ? selectedType.trim()
      : 'all';

  if (normalizedType === 'all') {
    return normalized;
  }

  return normalized.filter((item) => item.formType === normalizedType);
}

/**
 * Fetch active public Google Forms configuration from Flask without any authentication headers.
 */
export async function fetchPublicEngagementForms(
  fetchImpl = globalThis.fetch,
  { formType = 'all' } = {}
) {
  if (typeof fetchImpl !== 'function') {
    throw new Error('Fetch implementation is required to load public forms.');
  }

  const normalizedType =
    typeof formType === 'string' && formType.trim() ? formType.trim() : 'all';

  const endpoint =
    normalizedType !== 'all' &&
    Object.prototype.hasOwnProperty.call(FORM_TYPE_PRIORITY, normalizedType)
      ? `/api/forms?type=${encodeURIComponent(normalizedType)}`
      : '/api/forms';

  const response = await fetchImpl(endpoint, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response || !response.ok) {
    throw new Error(
      `Failed to fetch public forms (HTTP ${response?.status ?? 'unknown'})`
    );
  }

  const payload = await response.json();
  const rawList = Array.isArray(payload)
    ? payload
    : Array.isArray(payload?.items)
      ? payload.items
      : [];

  return normalizeAndFilterEngagementForms(rawList, normalizedType);
}
