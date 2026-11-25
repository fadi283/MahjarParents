import React, { useState } from 'react';
import { CATEGORY_LABELS, formatArabicDate } from '../AnnouncementCard.jsx';
import {
  ADMIN_POST_CATEGORY_OPTIONS,
  validatePostInput,
} from '../../utils/adminValidation.js';
import { movePostInList, reorderPostsByDrag } from '../../utils/adminState.js';
import { FieldError, ItemRowActions, TOUCH_TARGET_STYLE } from './adminShared.jsx';

function extractInitialMediaUrls(item) {
  const rawLinks = item?.mediaLinks ?? item?.media_links;
  if (!Array.isArray(rawLinks)) return [''];
  const urls = rawLinks
    .map((entry) => {
      if (typeof entry === 'string') return entry.trim();
      if (entry && typeof entry === 'object') {
        return String(
          entry.canonicalUrl ||
            entry.canonical_url ||
            entry.originalUrl ||
            entry.original_url ||
            entry.embedUrl ||
            entry.embed_url ||
            entry.url ||
            ''
        ).trim();
      }
      return '';
    })
    .filter(Boolean);
  return urls.length > 0 ? urls : [''];
}

function buildPostFormState(item = null) {
  return {
    title: item?.title ?? '',
    category: item?.category ?? 'general',
    summary: item?.summary ?? item?.content ?? item?.description ?? '',
    eventDate: item?.eventDate ?? item?.event_date ?? '',
    imageUrl: item?.imageUrl ?? item?.image_url ?? '',
    mediaLinks: extractInitialMediaUrls(item),
  };
}

export default function PostsAdminPanel({
  posts = [],
  onCreate,
  onUpdate,
  onDelete,
  onReorder,
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
  const [draggedPostId, setDraggedPostId] = useState(null);
  const [dragOverPostId, setDragOverPostId] = useState(null);

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

  const handleMediaLinkChange = (index, value) => {
    setFormState((prev) => ({
      ...prev,
      mediaLinks: prev.mediaLinks.map((item, idx) => (idx === index ? value : item)),
    }));
    if (fieldErrors.mediaLinks) {
      setFieldErrors((prev) => ({ ...prev, mediaLinks: '' }));
    }
  };

  const handleAddMediaLink = () => {
    setFormState((prev) => ({
      ...prev,
      mediaLinks: [...prev.mediaLinks, ''],
    }));
  };

  const handleRemoveMediaLink = (index) => {
    setFormState((prev) => {
      if (prev.mediaLinks.length <= 1) {
        return { ...prev, mediaLinks: [''] };
      }
      return {
        ...prev,
        mediaLinks: prev.mediaLinks.filter((_, idx) => idx !== index),
      };
    });
    if (fieldErrors.mediaLinks) {
      setFieldErrors((prev) => ({ ...prev, mediaLinks: '' }));
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

  const commitReorder = async (orderedIds) => {
    if (typeof onReorder !== 'function' || !Array.isArray(orderedIds) || orderedIds.length === 0) {
      return;
    }
    await onReorder(orderedIds);
  };

  const handleDragStart = (event, postId) => {
    if (isBusy || posts.length < 2) {
      event.preventDefault();
      return;
    }
    const target = event.target;
    if (
      target &&
      typeof target.closest === 'function' &&
      target.closest('button, input, textarea, select, a') &&
      !target.closest('.admin-drag-handle')
    ) {
      event.preventDefault();
      return;
    }
    setDraggedPostId(postId);
    setDragOverPostId(postId);
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', String(postId));
    }
  };

  const handleDragOver = (event, postId) => {
    if (isBusy || posts.length < 2) return;
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move';
    }
    if (String(dragOverPostId) !== String(postId)) {
      setDragOverPostId(postId);
    }
  };

  const handleDrop = async (event, targetPostId) => {
    event.preventDefault();
    const sourceId = draggedPostId ?? event.dataTransfer?.getData('text/plain');
    setDraggedPostId(null);
    setDragOverPostId(null);
    if (sourceId === null || sourceId === undefined || sourceId === '') return;
    const { moved, orderedIds } = reorderPostsByDrag(posts, sourceId, targetPostId);
    if (moved) {
      await commitReorder(orderedIds);
    }
  };

  const handleDragEnd = () => {
    setDraggedPostId(null);
    setDragOverPostId(null);
  };

  const handleTouchStart = (postId) => {
    if (isBusy || posts.length < 2) return;
    setDraggedPostId(postId);
    setDragOverPostId(postId);
  };

  const handleTouchMove = (event) => {
    if (draggedPostId === null || typeof document === 'undefined') return;
    const touch = event.touches?.[0];
    if (!touch) return;
    const el = document.elementFromPoint(touch.clientX, touch.clientY);
    const hoveredPost = el?.closest?.('[data-post-id]');
    const hoveredId = hoveredPost?.getAttribute('data-post-id');
    if (hoveredId && String(dragOverPostId) !== String(hoveredId)) {
      setDragOverPostId(hoveredId);
    }
  };

  const handleTouchEnd = async () => {
    const sourceId = draggedPostId;
    const targetId = dragOverPostId;
    setDraggedPostId(null);
    setDragOverPostId(null);
    if (
      sourceId === null ||
      targetId === null ||
      String(sourceId) === String(targetId)
    ) {
      return;
    }
    const { moved, orderedIds } = reorderPostsByDrag(posts, sourceId, targetId);
    if (moved) {
      await commitReorder(orderedIds);
    }
  };

  const handleTouchCancel = () => {
    setDraggedPostId(null);
    setDragOverPostId(null);
  };

  const handleDragHandleKeyDown = async (event, postId) => {
    if (isBusy || posts.length < 2) return;
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
    event.preventDefault();
    const direction = event.key === 'ArrowUp' ? 'up' : 'down';
    const { moved, orderedIds } = movePostInList(posts, postId, direction);
    if (moved) {
      await commitReorder(orderedIds);
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

          <div className="admin-field">
            <label htmlFor="post-media-link-0" className="admin-field__label">
              روابط الوسائط الخارجية (اختياري)
            </label>
            <span className="admin-field__hint">
              يمكنك لصق رابط فيديو أو رييل أو منشور أو صورة أو صوت من المنصات المعتمدة (YouTube، Instagram، Facebook، TikTok، X، وغيرها) — يتم التعرف على النوع تلقائياً دون الحاجة لتحديده.
            </span>
            <div className="admin-media-list">
              {formState.mediaLinks.map((mediaUrl, idx) => (
                <div key={idx} className="admin-media-row">
                  <input
                    id={`post-media-link-${idx}`}
                    type="url"
                    dir="ltr"
                    className="admin-input admin-media-row__input"
                    placeholder="https://..."
                    value={mediaUrl}
                    onChange={(e) => handleMediaLinkChange(idx, e.target.value)}
                    disabled={isBusy}
                    aria-label={`رابط وسائط خارجي ${idx + 1}`}
                  />
                  {(formState.mediaLinks.length > 1 || Boolean(mediaUrl.trim())) && (
                    <button
                      type="button"
                      className="admin-btn admin-btn--danger-outline"
                      style={TOUCH_TARGET_STYLE}
                      onClick={() => handleRemoveMediaLink(idx)}
                      disabled={isBusy}
                    >
                      {formState.mediaLinks.length > 1 ? 'حذف' : 'مسح'}
                    </button>
                  )}
                </div>
              ))}
              <div>
                <button
                  type="button"
                  className="admin-btn admin-btn--secondary admin-media-add"
                  style={TOUCH_TARGET_STYLE}
                  onClick={handleAddMediaLink}
                  disabled={isBusy}
                >
                  + إضافة رابط وسائط آخر
                </button>
              </div>
            </div>
            <FieldError message={fieldErrors.mediaLinks} />
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
        {posts.length > 1 && (
          <p className="admin-list-section__hint">
            اسحب الإعلان وأفلته لتغيير ترتيبه في لوحة الإعلانات.
          </p>
        )}
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
              const isDraggable = !isBusy && posts.length > 1;
              const isDragging = draggedPostId !== null && String(draggedPostId) === String(post.id);
              const isDragOver =
                dragOverPostId !== null &&
                String(dragOverPostId) === String(post.id) &&
                !isDragging;
              const itemClassName = [
                'admin-item',
                posts.length > 1 ? 'admin-item--draggable' : '',
                isDragging ? 'admin-item--dragging' : '',
                isDragOver ? 'admin-item--drag-over' : '',
              ]
                .filter(Boolean)
                .join(' ');
              return (
                <article
                  key={post.id}
                  className={itemClassName}
                  role="listitem"
                  draggable={isDraggable}
                  data-post-id={post.id}
                  onDragStart={(e) => handleDragStart(e, post.id)}
                  onDragOver={(e) => handleDragOver(e, post.id)}
                  onDragEnter={(e) => handleDragOver(e, post.id)}
                  onDrop={(e) => handleDrop(e, post.id)}
                  onDragEnd={handleDragEnd}
                >
                  <div className="admin-item__row">
                    {posts.length > 1 && (
                      <span
                        className="admin-drag-handle"
                        role="button"
                        tabIndex={0}
                        style={{ ...TOUCH_TARGET_STYLE, touchAction: 'none' }}
                        title="اسحب لتغيير الترتيب"
                        aria-label={`اسحب لتغيير ترتيب الإعلان ${post.title}`}
                        onKeyDown={(e) => handleDragHandleKeyDown(e, post.id)}
                        onTouchStart={() => handleTouchStart(post.id)}
                        onTouchMove={handleTouchMove}
                        onTouchEnd={handleTouchEnd}
                        onTouchCancel={handleTouchCancel}
                      >
                        ⋮⋮
                      </span>
                    )}
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
