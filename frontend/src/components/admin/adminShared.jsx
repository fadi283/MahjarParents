import React, { useState } from 'react';
import { moveItemInList, reorderItemsByDrag } from '../../utils/adminState.js';

export const TOUCH_TARGET_STYLE = {
  minHeight: '44px',
  minWidth: '44px',
};

export function useDragReorder({
  items = [],
  isBusy = false,
  onReorder,
  dataAttribute = 'data-item-id',
}) {
  const [draggedId, setDraggedId] = useState(null);
  const [dragOverId, setDragOverId] = useState(null);

  const canReorder = !isBusy && items.length > 1;

  const commitReorder = async (orderedIds) => {
    if (
      typeof onReorder !== 'function' ||
      !Array.isArray(orderedIds) ||
      orderedIds.length === 0
    ) {
      return;
    }
    await onReorder(orderedIds);
  };

  const resetDrag = () => {
    setDraggedId(null);
    setDragOverId(null);
  };

  const handleDragStart = (event, itemId) => {
    if (!canReorder) {
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
    setDraggedId(itemId);
    setDragOverId(itemId);
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', String(itemId));
    }
  };

  const handleDragOver = (event, itemId) => {
    if (!canReorder) return;
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'move';
    }
    if (String(dragOverId) !== String(itemId)) {
      setDragOverId(itemId);
    }
  };

  const handleDrop = async (event, targetItemId) => {
    event.preventDefault();
    const sourceId = draggedId ?? event.dataTransfer?.getData('text/plain');
    resetDrag();
    if (sourceId === null || sourceId === undefined || sourceId === '') return;
    const { moved, orderedIds } = reorderItemsByDrag(items, sourceId, targetItemId);
    if (moved) {
      await commitReorder(orderedIds);
    }
  };

  const handleTouchStart = (itemId) => {
    if (!canReorder) return;
    setDraggedId(itemId);
    setDragOverId(itemId);
  };

  const handleTouchMove = (event) => {
    if (draggedId === null || typeof document === 'undefined') return;
    const touch = event.touches?.[0];
    if (!touch) return;
    const el = document.elementFromPoint(touch.clientX, touch.clientY);
    const hoveredItem = el?.closest?.(`[${dataAttribute}]`);
    const hoveredId = hoveredItem?.getAttribute(dataAttribute);
    if (hoveredId && String(dragOverId) !== String(hoveredId)) {
      setDragOverId(hoveredId);
    }
  };

  const handleTouchEnd = async () => {
    const sourceId = draggedId;
    const targetId = dragOverId;
    resetDrag();
    if (
      sourceId === null ||
      targetId === null ||
      String(sourceId) === String(targetId)
    ) {
      return;
    }
    const { moved, orderedIds } = reorderItemsByDrag(items, sourceId, targetId);
    if (moved) {
      await commitReorder(orderedIds);
    }
  };

  const handleKeyDown = async (event, itemId) => {
    if (!canReorder) return;
    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
    event.preventDefault();
    const direction = event.key === 'ArrowUp' ? 'up' : 'down';
    const { moved, orderedIds } = moveItemInList(items, itemId, direction);
    if (moved) {
      await commitReorder(orderedIds);
    }
  };

  const getItemDragState = (itemId) => {
    const isDragging = draggedId !== null && String(draggedId) === String(itemId);
    const isDragOver =
      dragOverId !== null && String(dragOverId) === String(itemId) && !isDragging;
    const className = [
      'admin-item',
      items.length > 1 ? 'admin-item--draggable' : '',
      isDragging ? 'admin-item--dragging' : '',
      isDragOver ? 'admin-item--drag-over' : '',
    ]
      .filter(Boolean)
      .join(' ');
    return { isDraggable: canReorder, isDragging, isDragOver, className };
  };

  return {
    canReorder,
    getItemDragState,
    handleDragStart,
    handleDragOver,
    handleDrop,
    handleDragEnd: resetDrag,
    handleTouchStart,
    handleTouchMove,
    handleTouchEnd,
    handleTouchCancel: resetDrag,
    handleKeyDown,
  };
}

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
