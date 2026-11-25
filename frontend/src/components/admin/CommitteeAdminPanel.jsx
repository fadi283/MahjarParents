import React, { useState } from 'react';
import { validateCommitteeInput } from '../../utils/adminValidation.js';
import {
  FieldError,
  ItemRowActions,
  TOUCH_TARGET_STYLE,
  useDragReorder,
} from './adminShared.jsx';

function buildCommitteeFormState(item = null) {
  return {
    fullName: item?.fullName ?? item?.full_name ?? '',
    role: item?.role ?? item?.title ?? '',
    responsibilitySummary:
      item?.responsibilitySummary ?? item?.responsibility_summary ?? '',
    email: item?.email ?? item?.contactUrl ?? item?.contact_url ?? '',
    phone: item?.phone ?? '',
    isDirectContact: Boolean(item?.isDirectContact ?? item?.is_direct_contact),
    avatarUrl: item?.avatarUrl ?? item?.avatar_url ?? '',
  };
}

export default function CommitteeAdminPanel({
  members = [],
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
    buildCommitteeFormState(initialEditingItem)
  );
  const [fieldErrors, setFieldErrors] = useState({});
  const [uploadStatus, setUploadStatus] = useState('');
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const drag = useDragReorder({
    items: members,
    isBusy,
    onReorder,
    dataAttribute: 'data-member-id',
  });

  const isEditing = editingId !== null && editingId !== undefined;

  const resetForm = () => {
    setEditingId(null);
    setFormState(buildCommitteeFormState(null));
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
        handleFieldChange('avatarUrl', uploadedUrl);
        setUploadStatus('تم رفع الصورة وتحسينها بنجاح.');
      } else {
        setUploadStatus('');
      }
    } catch {
      setUploadStatus('');
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const validation = validateCommitteeInput(formState);
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

  const handleStartEdit = (member) => {
    setEditingId(member.id);
    setFormState(buildCommitteeFormState(member));
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
    <section dir="rtl" className="admin-panel" aria-labelledby="admin-committee-heading">
      <div className="admin-card">
        <div className="admin-card__header">
          <h3 id="admin-committee-heading" className="admin-card__title">
            {isEditing ? 'تعديل بيانات عضو اللجنة' : 'إضافة عضو لجنة جديد'}
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
              <label htmlFor="committee-fullname" className="admin-field__label">
                الاسم الكامل *
              </label>
              <input
                id="committee-fullname"
                type="text"
                className="admin-input"
                value={formState.fullName}
                onChange={(e) => handleFieldChange('fullName', e.target.value)}
                disabled={isBusy}
                required
              />
              <FieldError message={fieldErrors.fullName} />
            </div>

            <div className="admin-field">
              <label htmlFor="committee-role" className="admin-field__label">
                الدور / الصفة الوظيفية *
              </label>
              <input
                id="committee-role"
                type="text"
                className="admin-input"
                value={formState.role}
                onChange={(e) => handleFieldChange('role', e.target.value)}
                disabled={isBusy}
                required
              />
              <FieldError message={fieldErrors.role} />
            </div>

            <div className="admin-field">
              <label htmlFor="committee-email" className="admin-field__label">
                البريد الإلكتروني (اختياري)
              </label>
              <input
                id="committee-email"
                type="email"
                dir="ltr"
                className="admin-input"
                value={formState.email}
                onChange={(e) => handleFieldChange('email', e.target.value)}
                disabled={isBusy}
              />
              <FieldError message={fieldErrors.email} />
            </div>

            <div className="admin-field">
              <label htmlFor="committee-phone" className="admin-field__label">
                رقم الهاتف (اختياري)
              </label>
              <input
                id="committee-phone"
                type="text"
                dir="ltr"
                className="admin-input"
                value={formState.phone}
                onChange={(e) => handleFieldChange('phone', e.target.value)}
                disabled={isBusy}
              />
              <FieldError message={fieldErrors.phone} />
            </div>

            <div className="admin-field">
              <label htmlFor="committee-avatar" className="admin-field__label">
                رابط الصورة الشخصية (اختياري)
              </label>
              <input
                id="committee-avatar"
                type="url"
                dir="ltr"
                className="admin-input"
                placeholder="https://... أو /api/media/images/..."
                value={formState.avatarUrl}
                onChange={(e) => handleFieldChange('avatarUrl', e.target.value)}
                disabled={isBusy}
              />
              <FieldError message={fieldErrors.avatarUrl} />
              {typeof onUploadImage === 'function' && (
                <div className="admin-upload">
                  <label htmlFor="committee-avatar-file" className="admin-upload__label">
                    أو رفع صورة لتحسينها تلقائياً:
                  </label>
                  <input
                    id="committee-avatar-file"
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
            <label htmlFor="committee-direct-contact" className="admin-field__label">
              <input
                id="committee-direct-contact"
                type="checkbox"
                checked={formState.isDirectContact}
                onChange={(e) => handleFieldChange('isDirectContact', e.target.checked)}
                disabled={isBusy}
              />{' '}
              جهة اتصال مباشرة (تظهر في صفحة التواصل مع أزرار الاتصال والواتساب والبريد)
            </label>
          </div>

          <div className="admin-field">
            <label htmlFor="committee-summary" className="admin-field__label">
              نبذة عن المهام والمسؤوليات
            </label>
            <textarea
              id="committee-summary"
              rows={3}
              className="admin-textarea"
              value={formState.responsibilitySummary}
              onChange={(e) => handleFieldChange('responsibilitySummary', e.target.value)}
              disabled={isBusy}
            />
            <FieldError message={fieldErrors.responsibilitySummary} />
          </div>

          <div className="admin-form__actions">
            <button
              type="submit"
              className="admin-btn admin-btn--primary"
              style={TOUCH_TARGET_STYLE}
              disabled={isBusy}
            >
              {isEditing ? 'حفظ التعديلات' : 'إضافة عضو اللجنة'}
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
          قائمة أعضاء اللجنة ({members.length})
        </h4>
        {members.length > 1 && (
          <p className="admin-list-section__hint">
            اسحب عضو اللجنة وأفلته لتغيير ترتيبه في دليل اللجنة.
          </p>
        )}
        {members.length === 0 ? (
          <div className="admin-empty" role="status">
            لا يوجد أعضاء مسجلون في اللجنة حالياً.
          </div>
        ) : (
          <div className="admin-list" role="list">
            {members.map((member) => {
              const name = member.fullName ?? member.full_name ?? '';
              const role = member.role ?? member.title ?? '';
              const summary =
                member.responsibilitySummary ?? member.responsibility_summary ?? '';
              const { isDraggable, className } = drag.getItemDragState(member.id);
              return (
                <article
                  key={member.id}
                  className={className}
                  role="listitem"
                  draggable={isDraggable}
                  data-member-id={member.id}
                  onDragStart={(e) => drag.handleDragStart(e, member.id)}
                  onDragOver={(e) => drag.handleDragOver(e, member.id)}
                  onDragEnter={(e) => drag.handleDragOver(e, member.id)}
                  onDrop={(e) => drag.handleDrop(e, member.id)}
                  onDragEnd={drag.handleDragEnd}
                >
                  <div className="admin-item__row">
                    {members.length > 1 && (
                      <span
                        className="admin-drag-handle"
                        role="button"
                        tabIndex={0}
                        style={{ ...TOUCH_TARGET_STYLE, touchAction: 'none' }}
                        title="اسحب لتغيير الترتيب"
                        aria-label={`اسحب لتغيير ترتيب عضو اللجنة ${name}`}
                        onKeyDown={(e) => drag.handleKeyDown(e, member.id)}
                        onTouchStart={() => drag.handleTouchStart(member.id)}
                        onTouchMove={drag.handleTouchMove}
                        onTouchEnd={drag.handleTouchEnd}
                        onTouchCancel={drag.handleTouchCancel}
                      >
                        ⋮⋮
                      </span>
                    )}
                    <div className="admin-item__body">
                      <div className="admin-item__top">
                        <strong className="admin-item__title">{name}</strong>
                        <span className="admin-badge">{role}</span>
                        {(member.isDirectContact ?? member.is_direct_contact) && (
                          <span className="admin-badge">جهة اتصال مباشرة</span>
                        )}
                      </div>
                      {summary && <p className="admin-item__desc">{summary}</p>}
                      <div className="admin-item__meta">
                        {member.email && (
                          <span>
                            البريد: <bdi dir="ltr">{member.email}</bdi>
                          </span>
                        )}
                        {member.phone && (
                          <span>
                            الهاتف: <bdi dir="ltr">{member.phone}</bdi>
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <ItemRowActions
                    itemId={member.id}
                    itemLabel={name}
                    confirmDeleteId={confirmDeleteId}
                    isBusy={isBusy}
                    onEdit={() => handleStartEdit(member)}
                    onRequestDelete={() => setConfirmDeleteId(member.id)}
                    onConfirmDelete={() => handleConfirmDelete(member.id)}
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
