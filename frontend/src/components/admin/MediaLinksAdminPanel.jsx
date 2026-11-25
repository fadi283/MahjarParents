import React, { useState } from 'react';
import { validateMediaLinkInput } from '../../utils/adminValidation.js';
import { FieldError, ItemRowActions, TOUCH_TARGET_STYLE } from './adminShared.jsx';

function buildMediaFormState(item = null) {
  return {
    url:
      item?.originalUrl ??
      item?.canonicalUrl ??
      item?.embedUrl ??
      item?.url ??
      '',
    title: item?.title ?? '',
    mediaType: item?.mediaType ?? item?.media_type ?? '',
    postId:
      item?.postId !== null && item?.postId !== undefined
        ? String(item.postId)
        : item?.post_id !== null && item?.post_id !== undefined
          ? String(item.post_id)
          : '',
  };
}

export default function MediaLinksAdminPanel({
  mediaLinks = [],
  posts = [],
  onCreate,
  onUpdate,
  onDelete,
  isBusy = false,
  initialEditingItem = null,
}) {
  const [editingId, setEditingId] = useState(initialEditingItem?.id ?? null);
  const [formState, setFormState] = useState(() =>
    buildMediaFormState(initialEditingItem)
  );
  const [fieldErrors, setFieldErrors] = useState({});
  const [filterPostId, setFilterPostId] = useState('all');
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  const isEditing = editingId !== null && editingId !== undefined;

  const resetForm = () => {
    setEditingId(null);
    setFormState(buildMediaFormState(null));
    setFieldErrors({});
  };

  const handleFieldChange = (field, value) => {
    setFormState((prev) => ({ ...prev, [field]: value }));
    if (fieldErrors[field]) {
      setFieldErrors((prev) => ({ ...prev, [field]: '' }));
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const validation = validateMediaLinkInput(formState);
    if (!validation.valid) {
      setFieldErrors(validation.errors);
      return;
    }
    setFieldErrors({});

    let ok = false;
    if (isEditing && typeof onUpdate === 'function') {
      ok = await onUpdate(editingId, validation.payload);
    } else if (typeof onCreate === 'function') {
      ok = await onCreate(validation.payload);
    }

    if (ok !== false) {
      resetForm();
    }
  };

  const handleStartEdit = (link) => {
    setEditingId(link.id);
    setFormState(buildMediaFormState(link));
    setFieldErrors({});
    setConfirmDeleteId(null);
  };

  const handleConfirmDelete = async (id) => {
    if (typeof onDelete === 'function') {
      const ok = await onDelete(id);
      if (ok !== false) {
        setConfirmDeleteId(null);
        if (String(editingId) === String(id)) {
          resetForm();
        }
      }
    }
  };

  const postTitleById = new Map(posts.map((post) => [String(post.id), post.title]));
  const visibleLinks =
    filterPostId === 'all'
      ? mediaLinks
      : filterPostId === 'standalone'
        ? mediaLinks.filter((link) => link.postId === null || link.postId === undefined)
        : mediaLinks.filter((link) => String(link.postId) === String(filterPostId));

  return (
    <section dir="rtl" className="admin-panel" aria-labelledby="admin-media-heading">
      <div className="admin-card">
        <div className="admin-card__header">
          <h3 id="admin-media-heading" className="admin-card__title">
            {isEditing ? 'تعديل رابط الوسائط الخارجي' : 'إضافة رابط وسائط خارجي'}
          </h3>
          {isEditing && (
            <button
              type="button"
              className="admin-btn admin-btn--ghost"
              style={TOUCH_TARGET_STYLE}
              onClick={resetForm}
              disabled={isBusy}
            >
              إلغاء التعديل
            </button>
          )}
        </div>

        <form className="admin-form" onSubmit={handleSubmit} noValidate>
          <div className="admin-form__grid">
            <div className="admin-field">
              <label htmlFor="media-url" className="admin-field__label">
                رابط الوسائط (HTTPS) *
              </label>
              <input
                id="media-url"
                type="url"
                dir="ltr"
                className="admin-input"
                placeholder="https://www.youtube.com/watch?v=..."
                value={formState.url}
                onChange={(e) => handleFieldChange('url', e.target.value)}
                disabled={isBusy}
                required
              />
              <span className="admin-field__hint">
                المنصات المعتمدة: YouTube وVimeo (فيديو) أو SoundCloud وGoogle Drive (صوت).
              </span>
              <FieldError message={fieldErrors.url} />
            </div>

            <div className="admin-field">
              <label htmlFor="media-title" className="admin-field__label">
                عنوان الوسائط (اختياري)
              </label>
              <input
                id="media-title"
                type="text"
                className="admin-input"
                value={formState.title}
                onChange={(e) => handleFieldChange('title', e.target.value)}
                disabled={isBusy}
              />
              <FieldError message={fieldErrors.title} />
            </div>

            <div className="admin-field">
              <label htmlFor="media-type" className="admin-field__label">
                نوع الوسائط
              </label>
              <select
                id="media-type"
                className="admin-select"
                value={formState.mediaType}
                onChange={(e) => handleFieldChange('mediaType', e.target.value)}
                disabled={isBusy}
              >
                <option value="">تحديد تلقائي حسب الرابط</option>
                <option value="video">فيديو</option>
                <option value="audio">صوت</option>
              </select>
              <FieldError message={fieldErrors.mediaType} />
            </div>

            <div className="admin-field">
              <label htmlFor="media-post-id" className="admin-field__label">
                ربط بإعلان أو فعالية (اختياري)
              </label>
              <select
                id="media-post-id"
                className="admin-select"
                value={formState.postId}
                onChange={(e) => handleFieldChange('postId', e.target.value)}
                disabled={isBusy}
              >
                <option value="">رابط مستقل (غير مرتبط بإعلان)</option>
                {posts.map((post) => (
                  <option key={post.id} value={String(post.id)}>
                    {post.title}
                  </option>
                ))}
              </select>
              <FieldError message={fieldErrors.postId} />
            </div>
          </div>

          <div className="admin-form__actions">
            <button
              type="submit"
              className="admin-btn admin-btn--primary"
              style={TOUCH_TARGET_STYLE}
              disabled={isBusy}
            >
              {isEditing ? 'حفظ التعديلات' : 'إضافة رابط الوسائط'}
            </button>
            {isEditing && (
              <button
                type="button"
                className="admin-btn admin-btn--secondary"
                style={TOUCH_TARGET_STYLE}
                onClick={resetForm}
                disabled={isBusy}
              >
                إلغاء التعديل
              </button>
            )}
          </div>
        </form>
      </div>

      <div className="admin-list-section">
        <div className="admin-list-section__header">
          <h4 className="admin-list-section__title">
            روابط الوسائط المحفوظة ({visibleLinks.length})
          </h4>
          <div className="admin-filter">
            <label htmlFor="media-filter-post" className="admin-filter__label">
              تصفية حسب الإعلان:
            </label>
            <select
              id="media-filter-post"
              className="admin-select admin-select--compact"
              value={filterPostId}
              onChange={(e) => setFilterPostId(e.target.value)}
            >
              <option value="all">جميع الروابط</option>
              <option value="standalone">روابط مستقلة فقط</option>
              {posts.map((post) => (
                <option key={post.id} value={String(post.id)}>
                  {post.title}
                </option>
              ))}
            </select>
          </div>
        </div>

        {visibleLinks.length === 0 ? (
          <div className="admin-empty" role="status">
            لا توجد روابط وسائط مطابقة للتصفية الحالية.
          </div>
        ) : (
          <div className="admin-list" role="list">
            {visibleLinks.map((link) => {
              const linkedTitle =
                link.postId !== null && link.postId !== undefined
                  ? postTitleById.get(String(link.postId)) || `إعلان #${link.postId}`
                  : 'رابط مستقل';
              const displayUrl = link.canonicalUrl || link.embedUrl || link.url || '';
              const typeLabel = link.mediaType === 'audio' ? 'صوت' : 'فيديو';

              return (
                <article key={link.id} className="admin-item" role="listitem">
                  <div className="admin-item__body">
                    <div className="admin-item__top">
                      <strong className="admin-item__title">
                        {link.title || 'رابط وسائط بدون عنوان'}
                      </strong>
                      <span className="admin-badge">{typeLabel}</span>
                      {link.provider && (
                        <span className="admin-badge admin-badge--muted">
                          {link.provider}
                        </span>
                      )}
                    </div>
                    <p className="admin-item__url" dir="ltr">
                      {displayUrl}
                    </p>
                    <div className="admin-item__meta">
                      <span>الارتباط: {linkedTitle}</span>
                    </div>
                  </div>
                  <ItemRowActions
                    itemId={link.id}
                    itemLabel={link.title || displayUrl}
                    confirmDeleteId={confirmDeleteId}
                    isBusy={isBusy}
                    onEdit={() => handleStartEdit(link)}
                    onRequestDelete={() => setConfirmDeleteId(link.id)}
                    onConfirmDelete={() => handleConfirmDelete(link.id)}
                    onCancelDelete={() => setConfirmDeleteId(null)}
                  />
                </article>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
