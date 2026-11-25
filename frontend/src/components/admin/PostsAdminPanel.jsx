import React, { useState } from 'react';
import { CATEGORY_LABELS, formatArabicDate } from '../AnnouncementCard.jsx';
import {
  ADMIN_POST_CATEGORY_OPTIONS,
  validatePostInput,
} from '../../utils/adminValidation.js';
import { FieldError, ItemRowActions, TOUCH_TARGET_STYLE } from './adminShared.jsx';

function buildPostFormState(item = null) {
  return {
    title: item?.title ?? '',
    category: item?.category ?? 'general',
    summary: item?.summary ?? item?.content ?? item?.description ?? '',
    eventDate: item?.eventDate ?? item?.event_date ?? '',
    imageUrl: item?.imageUrl ?? item?.image_url ?? '',
  };
}

export default function PostsAdminPanel({
  posts = [],
  onCreate,
  onUpdate,
  onDelete,
  onUploadImage,
  isBusy = false,
  initialEditingItem = null,
}) {
  const [editingId, setEditingId] = useState(initialEditingItem?.id ?? null);
  const [formState, setFormState] = useState(() =>
    buildPostFormState(initialEditingItem)
  );
  const [fieldErrors, setFieldErrors] = useState({});
  const [uploadStatus, setUploadStatus] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  const isEditing = editingId !== null && editingId !== undefined;

  const resetForm = () => {
    setEditingId(null);
    setFormState(buildPostFormState(null));
    setFieldErrors({});
    setUploadStatus('');
  };

  const handleFieldChange = (field, value) => {
    setFormState((prev) => ({ ...prev, [field]: value }));
    if (fieldErrors[field]) {
      setFieldErrors((prev) => ({ ...prev, [field]: '' }));
    }
  };

  const handleImageFileChange = async (event) => {
    const file = event.target.files?.[0];
    if (!file || typeof onUploadImage !== 'function') return;
    setUploadStatus('جارٍ ضغط ورفع الصورة...');
    try {
      const uploadedUrl = await onUploadImage(file);
      if (uploadedUrl) {
        handleFieldChange('imageUrl', uploadedUrl);
        setUploadStatus('تم رفع الصورة وتحسينها بصيغة WebP بنجاح.');
      } else {
        setUploadStatus('');
      }
    } catch {
      setUploadStatus('');
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const validation = validatePostInput(formState);
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

  const handleStartEdit = (post) => {
    setEditingId(post.id);
    setFormState(buildPostFormState(post));
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

  return (
    <section dir="rtl" className="admin-panel" aria-labelledby="admin-posts-heading">
      <div className="admin-card">
        <div className="admin-card__header">
          <h3 id="admin-posts-heading" className="admin-card__title">
            {isEditing ? 'تعديل الإعلان أو الفعالية' : 'إضافة إعلان أو فعالية جديدة'}
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
              <label htmlFor="post-title" className="admin-field__label">
                عنوان الإعلان *
              </label>
              <input
                id="post-title"
                type="text"
                className="admin-input"
                value={formState.title}
                onChange={(e) => handleFieldChange('title', e.target.value)}
                disabled={isBusy}
                required
              />
              <FieldError message={fieldErrors.title} />
            </div>

            <div className="admin-field">
              <label htmlFor="post-category" className="admin-field__label">
                التصنيف *
              </label>
              <select
                id="post-category"
                className="admin-select"
                value={formState.category}
                onChange={(e) => handleFieldChange('category', e.target.value)}
                disabled={isBusy}
              >
                {ADMIN_POST_CATEGORY_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
              <FieldError message={fieldErrors.category} />
            </div>

            <div className="admin-field">
              <label htmlFor="post-event-date" className="admin-field__label">
                تاريخ الفعالية (اختياري)
              </label>
              <input
                id="post-event-date"
                type="date"
                dir="ltr"
                className="admin-input"
                value={formState.eventDate}
                onChange={(e) => handleFieldChange('eventDate', e.target.value)}
                disabled={isBusy}
              />
              <FieldError message={fieldErrors.eventDate} />
            </div>

            <div className="admin-field">
              <label htmlFor="post-image-url" className="admin-field__label">
                رابط الصورة (اختياري)
              </label>
              <input
                id="post-image-url"
                type="url"
                dir="ltr"
                className="admin-input"
                placeholder="https://... أو /api/media/images/..."
                value={formState.imageUrl}
                onChange={(e) => handleFieldChange('imageUrl', e.target.value)}
                disabled={isBusy}
              />
              <FieldError message={fieldErrors.imageUrl} />
              {typeof onUploadImage === 'function' && (
                <div className="admin-upload">
                  <label htmlFor="post-image-file" className="admin-upload__label">
                    أو رفع صورة لتحسينها تلقائياً:
                  </label>
                  <input
                    id="post-image-file"
                    type="file"
                    accept="image/jpeg,image/png,image/webp,image/bmp"
                    className="admin-upload__input"
                    onChange={handleImageFileChange}
                    disabled={isBusy}
                  />
                  {uploadStatus && <span className="admin-field__hint">{uploadStatus}</span>}
                </div>
              )}
            </div>
          </div>

          <div className="admin-field">
            <label htmlFor="post-summary" className="admin-field__label">
              نص الإعلان أو التفاصيل *
            </label>
            <textarea
              id="post-summary"
              rows={4}
              className="admin-textarea"
              value={formState.summary}
              onChange={(e) => handleFieldChange('summary', e.target.value)}
              disabled={isBusy}
              required
            />
            <FieldError message={fieldErrors.summary} />
          </div>

          <div className="admin-form__actions">
            <button
              type="submit"
              className="admin-btn admin-btn--primary"
              style={TOUCH_TARGET_STYLE}
              disabled={isBusy}
            >
              {isEditing ? 'حفظ التعديلات' : 'نشر الإعلان'}
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
        <h4 className="admin-list-section__title">
          الإعلانات والفعاليات المنشورة ({posts.length})
        </h4>
        {posts.length === 0 ? (
          <div className="admin-empty" role="status">
            لا توجد إعلانات أو فعاليات منشورة حالياً.
          </div>
        ) : (
          <div className="admin-list" role="list">
            {posts.map((post) => {
              const catLabel = CATEGORY_LABELS[post.category] ?? CATEGORY_LABELS.general;
              const publishedAt = post.publishedAt ?? post.published_at ?? '';
              const eventDate = post.eventDate ?? post.event_date ?? '';
              const mediaCount = Array.isArray(post.mediaLinks) ? post.mediaLinks.length : 0;
              return (
                <article key={post.id} className="admin-item" role="listitem">
                  <div className="admin-item__body">
                    <div className="admin-item__top">
                      <strong className="admin-item__title">{post.title}</strong>
                      <span className="admin-badge">{catLabel}</span>
                    </div>
                    <p className="admin-item__desc">{post.summary}</p>
                    <div className="admin-item__meta">
                      {publishedAt && <span>النشر: {formatArabicDate(publishedAt)}</span>}
                      {eventDate && <span>موعد الفعالية: {formatArabicDate(eventDate)}</span>}
                      <span>روابط الوسائط: {mediaCount}</span>
                    </div>
                  </div>
                  <ItemRowActions
                    itemId={post.id}
                    itemLabel={post.title}
                    confirmDeleteId={confirmDeleteId}
                    isBusy={isBusy}
                    onEdit={() => handleStartEdit(post)}
                    onRequestDelete={() => setConfirmDeleteId(post.id)}
                    onConfirmDelete={() => handleConfirmDelete(post.id)}
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
