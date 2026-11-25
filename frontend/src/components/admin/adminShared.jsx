import React from 'react';

export const TOUCH_TARGET_STYLE = {
  minHeight: '44px',
  minWidth: '44px',
};

export function FieldError({ message }) {
  if (!message) return null;
  return (
    <span className="admin-field__error" role="alert">
      {message}
    </span>
  );
}

export function ItemRowActions({
  itemId,
  itemLabel,
  confirmDeleteId,
  onEdit,
  onRequestDelete,
  onConfirmDelete,
  onCancelDelete,
  isBusy = false,
}) {
  const isConfirming = String(confirmDeleteId) === String(itemId);

  return (
    <div className="admin-item__actions">
      <button
        type="button"
        className="admin-btn admin-btn--secondary"
        style={TOUCH_TARGET_STYLE}
        disabled={isBusy}
        onClick={onEdit}
        aria-label={`تعديل ${itemLabel}`}
      >
        تعديل
      </button>

      {isConfirming ? (
        <>
          <button
            type="button"
            className="admin-btn admin-btn--danger"
            style={TOUCH_TARGET_STYLE}
            disabled={isBusy}
            onClick={onConfirmDelete}
            aria-label={`تأكيد حذف ${itemLabel}`}
          >
            تأكيد الحذف
          </button>
          <button
            type="button"
            className="admin-btn admin-btn--ghost"
            style={TOUCH_TARGET_STYLE}
            disabled={isBusy}
            onClick={onCancelDelete}
          >
            إلغاء
          </button>
        </>
      ) : (
        <button
          type="button"
          className="admin-btn admin-btn--danger-outline"
          style={TOUCH_TARGET_STYLE}
          disabled={isBusy}
          onClick={onRequestDelete}
          aria-label={`حذف ${itemLabel}`}
        >
          حذف
        </button>
      )}
    </div>
  );
}
