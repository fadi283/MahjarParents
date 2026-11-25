import { buildApiUrl, resolveApiBaseUrl } from './apiConfig.js';

export const ADMIN_TOKEN_STORAGE_KEY = 'mahjar_admin_token';

const ERROR_MESSAGES_AR = {
  INVALID_CREDENTIALS: 'اسم المستخدم أو كلمة المرور غير صحيحة.',
  MISSING_CREDENTIALS: 'يرجى إدخال اسم المستخدم وكلمة المرور.',
  ADMIN_AUTH_NOT_CONFIGURED: 'إعدادات المصادقة غير مفعّلة على الخادم حالياً.',
  UNAUTHORIZED: 'يرجى تسجيل الدخول للمتابعة إلى لوحة الإدارة.',
  TOKEN_EXPIRED: 'انتهت صلاحية جلسة الإدارة، يرجى تسجيل الدخول مجدداً.',
  TOKEN_REVOKED: 'تم تسجيل الخروج من هذه الجلسة، يرجى تسجيل الدخول مجدداً.',
  INVALID_TOKEN: 'رمز الجلسة غير صالح، يرجى تسجيل الدخول مجدداً.',
  UNTRUSTED_FORM_DOMAIN: 'رابط النموذج غير مسموح به. يُسمح فقط بروابط Google Forms المعتمدة (docs.google.com/forms أو forms.gle).',
  INSECURE_FORM_URL: 'يجب أن يستخدم رابط Google Forms بروتوكول HTTPS.',
  INVALID_FORM_URL: 'رابط نموذج Google Forms غير صالح.',
  UNTRUSTED_MEDIA_DOMAIN:
    'رابط الوسائط من نطاق غير مسموح به أو صيغته غير مدعومة. المنصات المعتمدة تشمل: YouTube، Instagram، Facebook، TikTok، X، Threads، LinkedIn، Telegram، Vimeo، Dailymotion، SoundCloud، Spotify، Google Drive، Google Photos، Canva، بالإضافة إلى روابط الصور الخارجية الآمنة HTTPS.',
  INVALID_MEDIA_TYPE: 'نوع الوسائط المحدد غير صالح.',
  MEDIA_TYPE_MISMATCH: 'نوع الوسائط المحدد لا يتوافق مع محتوى الرابط المدخل.',
  INSECURE_MEDIA_URL: 'يجب أن يستخدم رابط الوسائط بروتوكول HTTPS.',
  RAW_AV_NOT_ALLOWED:
    'لا يُسمح برفع ملفات الفيديو أو الصوت الخام مباشرة؛ يرجى استضافتها خارجياً وإضافة الرابط فقط.',
  FILE_TOO_LARGE: 'حجم الصورة يتجاوز الحد الأقصى المسموح به.',
  UNSUPPORTED_MEDIA_TYPE: 'نوع الملف غير مدعوم. يُسمح فقط بصور JPEG أو PNG أو WebP أو BMP.',
  NOT_FOUND: 'العنصر المطلوب غير موجود أو تم حذفه مسبقاً.',
  POST_NOT_FOUND: 'الإعلان المرتبط غير موجود.',
};

export class AdminApiError extends Error {
  constructor(message, { status = 500, code = 'API_ERROR', field = null } = {}) {
    super(message);
    this.name = 'AdminApiError';
    this.status = status;
    this.code = code;
    this.field = field;
    this.isAuthError = status === 401;
  }
}

export function translateAdminError(errorOrPayload) {
  if (!errorOrPayload) {
    return 'حدث خطأ غير متوقع أثناء التواصل مع الخادم.';
  }
  const code = errorOrPayload.code;
  if (code && ERROR_MESSAGES_AR[code]) {
    return ERROR_MESSAGES_AR[code];
  }
  if (errorOrPayload.status === 401) {
    return ERROR_MESSAGES_AR.UNAUTHORIZED;
  }
  if (typeof errorOrPayload.error === 'string' && errorOrPayload.error.trim()) {
    return errorOrPayload.error;
  }
  if (typeof errorOrPayload.message === 'string' && errorOrPayload.message.trim()) {
    return errorOrPayload.message;
  }
  return 'تعذر تنفيذ العملية المطلوبة. يرجى المحاولة مرة أخرى.';
}

function getDefaultStorage() {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function createAdminApiClient({
  fetchImpl = typeof fetch === 'function' ? fetch.bind(globalThis) : null,
  storage = getDefaultStorage(),
  baseUrl = resolveApiBaseUrl(),
} = {}) {
  const readToken = () => {
    if (!storage) return '';
    try {
      return storage.getItem(ADMIN_TOKEN_STORAGE_KEY) || '';
    } catch {
      return '';
    }
  };

  const writeToken = (token) => {
    if (!storage) return;
    try {
      if (token) {
        storage.setItem(ADMIN_TOKEN_STORAGE_KEY, token);
      } else {
        storage.removeItem(ADMIN_TOKEN_STORAGE_KEY);
      }
    } catch {
      // Ignore storage quota or private-mode restrictions
    }
  };

  const request = async (
    path,
    { method = 'GET', body = undefined, isFormData = false, clearAuthOn401 = true } = {}
  ) => {
    if (!fetchImpl) {
      throw new AdminApiError('خدمة الشبكة غير متاحة في هذه البيئة.', {
        status: 0,
        code: 'NETWORK_UNAVAILABLE',
      });
    }

    const headers = {};
    const token = readToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    let requestBody = body;
    if (body !== undefined && !isFormData) {
      headers['Content-Type'] = 'application/json';
      requestBody = JSON.stringify(body);
    }

    let response;
    try {
      response = await fetchImpl(buildApiUrl(path, baseUrl), {
        method,
        headers,
        body: requestBody,
        credentials: 'include',
      });
    } catch {
      throw new AdminApiError('تعذر الاتصال بالخادم، يرجى التحقق من الشبكة والمحاولة مجدداً.', {
        status: 0,
        code: 'NETWORK_ERROR',
      });
    }

    let payload = null;
    const contentType = response.headers?.get?.('content-type') || '';
    if (contentType.includes('application/json')) {
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
    } else if (typeof response.text === 'function') {
      try {
        const text = await response.text();
        payload = text ? JSON.parse(text) : null;
      } catch {
        payload = null;
      }
    }

    if (!response.ok) {
      if (response.status === 401 && clearAuthOn401) {
        writeToken('');
      }
      const code = payload?.code || (response.status === 401 ? 'UNAUTHORIZED' : 'API_ERROR');
      const field = payload?.field || null;
      const message = translateAdminError({
        code,
        status: response.status,
        error: payload?.error,
      });
      throw new AdminApiError(message, {
        status: response.status,
        code,
        field,
      });
    }

    return payload;
  };

  return {
    getStoredToken: readToken,
    clearStoredToken: () => writeToken(''),

    async login(username, password) {
      const result = await request('/api/admin/auth/login', {
        method: 'POST',
        body: { username, password },
        clearAuthOn401: false,
      });
      if (result?.token) {
        writeToken(result.token);
      }
      return result;
    },

    getSession() {
      return request('/api/admin/auth/me', { method: 'GET' });
    },

    async logout() {
      try {
        await request('/api/admin/auth/logout', { method: 'POST' });
      } finally {
        writeToken('');
      }
    },

    listCommittee() {
      return request('/api/admin/committee', { method: 'GET' });
    },

    createCommitteeMember(payload) {
      return request('/api/admin/committee', { method: 'POST', body: payload });
    },

    updateCommitteeMember(id, payload) {
      return request(`/api/admin/committee/${id}`, { method: 'PUT', body: payload });
    },

    deleteCommitteeMember(id) {
      return request(`/api/admin/committee/${id}`, { method: 'DELETE' });
    },

    reorderCommittee(memberIds) {
      return request('/api/admin/committee/reorder', {
        method: 'PUT',
        body: { memberIds },
      });
    },

    listPosts() {
      return request('/api/admin/posts', { method: 'GET' });
    },

    createPost(payload) {
      return request('/api/admin/posts', { method: 'POST', body: payload });
    },

    updatePost(id, payload) {
      return request(`/api/admin/posts/${id}`, { method: 'PUT', body: payload });
    },

    deletePost(id) {
      return request(`/api/admin/posts/${id}`, { method: 'DELETE' });
    },

    reorderPosts(postIds) {
      return request('/api/admin/posts/reorder', {
        method: 'PUT',
        body: { postIds },
      });
    },

    listMediaLinks(postId = null) {
      const query =
        postId !== null && postId !== undefined && String(postId).trim() !== ''
          ? `?post_id=${encodeURIComponent(String(postId))}`
          : '';
      return request(`/api/admin/media-links${query}`, { method: 'GET' });
    },

    createMediaLink(payload) {
      return request('/api/admin/media-links', { method: 'POST', body: payload });
    },

    updateMediaLink(id, payload) {
      return request(`/api/admin/media-links/${id}`, { method: 'PUT', body: payload });
    },

    deleteMediaLink(id) {
      return request(`/api/admin/media-links/${id}`, { method: 'DELETE' });
    },

    listForms() {
      return request('/api/admin/forms', { method: 'GET' });
    },

    createForm(payload) {
      return request('/api/admin/forms', { method: 'POST', body: payload });
    },

    updateForm(id, payload) {
      return request(`/api/admin/forms/${id}`, { method: 'PUT', body: payload });
    },

    deleteForm(id) {
      return request(`/api/admin/forms/${id}`, { method: 'DELETE' });
    },

    reorderForms(formIds) {
      return request('/api/admin/forms/reorder', {
        method: 'PUT',
        body: { formIds },
      });
    },

    uploadImage(file) {
      const formData = new FormData();
      formData.append('file', file);
      return request('/api/media/images', {
        method: 'POST',
        body: formData,
        isFormData: true,
        clearAuthOn401: false,
      });
    },
  };
}

export const adminApi = createAdminApiClient();
