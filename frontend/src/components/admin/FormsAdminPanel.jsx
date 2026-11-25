import React, { useState } from 'react';
import {
  FORM_TYPE_LABELS,
  FORM_TYPE_OPTIONS,
  validateGoogleFormInput,
} from '../../utils/adminValidation.js';
import { FieldError, ItemRowActions, TOUCH_TARGET_STYLE } from './adminShared.jsx';

function buildFormState(item = null) {
  return {
    formType: item?.formType ?? item?.form_type ?? 'feedback',
    title: item?.title ?? '',
    description: item?.description ?? '',
    embedUrl: item?.embedUrl ?? item?.embed_url ?? item?.canonicalUrl ?? '',
    active: item?.active !== undefined ? Boolean(item.active) : true,
    displayOrder:
      item?.displayOrder !== null && item?.displayOrder !== undefined
        ? String(item.displayOrder)
        : item?.display_order !== null && item?.display_order !== undefined
          ? String(item.display_order)
          : '',
  };
}

export default function FormsAdminPanel({
  forms = [],
  onCreate,
  onUpdate,
  onDelete,
  isBusy = false,
  initialEditingItem = null,
}) {
  const [editingId, setEditingId] = useState(initialEditingItem?.id ?? null);
  const [formState, setFormState] = useState(() =>
    buildFormState(initialEditingItem)
  );
  const [fieldErrors, setFieldErrors] = useState({});
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  const isEditing = editingId !== null && editingId !== undefined;

  const resetForm = () => {
    setEditingId(null);
    setFormState(buildFormState(null));
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
    const validation = validateGoogleFormInput(formState);
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

  const handleStartEdit = (formItem) => {
    setEditingId(formItem.id);
    setFormState(buildFormState(formItem));
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
    <section dir="rtl" className="admin-panel" aria-labelledby="admin-forms-heading">
      <div className="admin-card">
        <div className="admin-card__header">
          <h3 id="admin-forms-heading" className="admin-card__title">
            {isEditing ? 'تعديل رابط Google Form' : 'إضافة رابط Google Form جديد'}
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
              <label htmlFor="form-type" className="admin-field__label">
                نوع النموذج *
              </label>
              <select
                id="form-type"
                className="admin-select"
                value={formState.formType}
                onChange={(e) => handleFieldChange('formType', e.target.value)}
                disabled={isBusy}
              >
                {FORM_TYPE_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
              <FieldError message={fieldErrors.formType} />
            </div>

            <div className="admin-field">
              <label htmlFor="form-title" className="admin-field__label">
                عنوان النموذج *
              </label>
              <input
                id="form-title"
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
              <label htmlFor="form-embed-url" className="admin-field__label">
                رابط النموذج (docs.google.com/forms أو forms.gle) *
              </label>
              <input
                id="form-embed-url"
                type="url"
                dir="ltr"
                className="admin-input"
                placeholder="https://docs.google.com/forms/d/e/.../viewform أو https://forms.gle/..."
                value={formState.embedUrl}
                onChange={(e) => handleFieldChange('embedUrl', e.target.value)}
                disabled={isBusy}
                required
              />
              <span className="admin-field__hint">
                يُقبل فقط النطاق الرسمي docs.google.com/forms أو الروابط المختصرة forms.gle مع HTTPS.
              </span>
              <FieldError message={fieldErrors.embedUrl} />
            </div>

            <div className="admin-field">
              <label htmlFor="form-order" className="admin-field__label">
                ترتيب العرض (اختياري)
              </label>
              <input
                id="form-order"
                type="number"
                min="1"
                step="1"
                dir="ltr"
                className="admin-input"
                value={formState.displayOrder}
                onChange={(e) => handleFieldChange('displayOrder', e.target.value)}
                disabled={isBusy}
              />
              <FieldError message={fieldErrors.displayOrder} />
            </div>
          </div>

          <div className="admin-field">
            <label htmlFor="form-description" className="admin-field__label">
              وصف مختصر للأهالي (اختياري)
            </label>
            <textarea
              id="form-description"
              rows={2}
              className="admin-textarea"
              value={formState.description}
              onChange={(e) => handleFieldChange('description', e.target.value)}
              disabled={isBusy}
            />
            <FieldError message={fieldErrors.description} />
          </div>

          <div className="admin-checkbox-row">
            <input
              id="form-active"
              type="checkbox"
              className="admin-checkbox"
              checked={formState.active}
              onChange={(e) => handleFieldChange('active', e.target.checked)}
              disabled={isBusy}
            />
            <label htmlFor="form-active" className="admin-field__label">
              نموذج مفعّل وظاهر للأهالي على المنصة
            </label>
            <FieldError message={fieldErrors.active} />
          </div>

          <div className="admin-form__actions">
            <button
              type="submit"
              className="admin-btn admin-btn--primary"
              style={TOUCH_TARGET_STYLE}
              disabled={isBusy}
            >
              {isEditing ? 'حفظ التعديلات' : 'إضافة رابط النموذج'}
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
          النماذج المضمنة المسجلة ({forms.length})
        </h4>
        {forms.length === 0 ? (
          <div className="admin-empty" role="status">
            لا توجد روابط Google Forms مسجلة حالياً.
          </div>
        ) : (
          <div className="admin-list" role="list">
            {forms.map((formItem) => {
              const typeKey = formItem.formType ?? formItem.form_type ?? 'feedback';
              const typeLabel = FORM_TYPE_LABELS[typeKey] ?? typeKey;
              const embedUrl = formItem.embedUrl ?? formItem.embed_url ?? '';
              return (
                <article key={formItem.id} className="admin-item" role="listitem">
                  <div className="admin-item__body">
                    <div className="admin-item__top">
                      <strong className="admin-item__title">{formItem.title}</strong>
                      <span className="admin-badge">{typeLabel}</span>
                      <span
                        className={`admin-badge ${
                          formItem.active ? 'admin-badge--active' : 'admin-badge--muted'
                        }`}
                      >
                        {formItem.active ? 'مفعّل' : 'معطّل'}
                      </span>
                    </div>
                    {formItem.description && (
                      <p className="admin-item__desc">{formItem.description}</p>
                    )}
                    <p className="admin-item__url" dir="ltr">
                      {embedUrl}
                    </p>
                  </div>
                  <ItemRowActions
                    itemId={formItem.id}
                    itemLabel={formItem.title}
                    confirmDeleteId={confirmDeleteId}
                    isBusy={isBusy}
                    onEdit={() => handleStartEdit(formItem)}
                    onRequestDelete={() => setConfirmDeleteId(formItem.id)}
                    onConfirmDelete={() => handleConfirmDelete(formItem.id)}
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
