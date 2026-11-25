import React, { useEffect, useRef, useState } from 'react';
import {
  buildSharePayload,
  copyShareLink,
  executeShareButtonAction,
} from '../utils/whatsappShare.js';

const TOUCH_TARGET_STYLE = {
  minHeight: '44px',
  minWidth: '44px',
};

export default function ShareActions({
  item,
  entityType = 'post',
  baseUrl,
  className = '',
  menuAlign = 'start',
  initialMenuOpen = false,
  onShare,
}) {
  const payload = buildSharePayload(item, { baseUrl, entityType });
  const [menuOpen, setMenuOpen] = useState(initialMenuOpen);
  const [copied, setCopied] = useState(false);
  const containerRef = useRef(null);
  const copyTimerRef = useRef(null);

  useEffect(() => {
    if (!menuOpen || typeof document === 'undefined') return undefined;

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') {
        setMenuOpen(false);
      }
    };

    const handlePointerDown = (event) => {
      if (
        containerRef.current &&
        typeof containerRef.current.contains === 'function' &&
        !containerRef.current.contains(event.target)
      ) {
        setMenuOpen(false);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('touchstart', handlePointerDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('touchstart', handlePointerDown);
    };
  }, [menuOpen]);

  useEffect(() => {
    return () => {
      if (copyTimerRef.current) {
        clearTimeout(copyTimerRef.current);
      }
    };
  }, []);

  if (!payload) return null;

  const handleTriggerClick = async () => {
    const result = await executeShareButtonAction(item, {
      baseUrl,
      entityType,
    });

    if (result.action === 'open-menu') {
      if (result.status === 'fallback') {
        setMenuOpen(true);
      } else {
        setMenuOpen((prev) => !prev);
      }
      return;
    }

    setMenuOpen(false);
    if (typeof onShare === 'function') {
      onShare(result);
    }
  };

  const handleCopyLink = async () => {
    const result = await copyShareLink(payload.url);
    if (result.copied) {
      setCopied(true);
      if (copyTimerRef.current) {
        clearTimeout(copyTimerRef.current);
      }
      copyTimerRef.current = setTimeout(() => {
        setCopied(false);
      }, 2500);
      if (typeof onShare === 'function') {
        onShare({ method: 'copy', status: 'copied', payload });
      }
    } else if (typeof onShare === 'function') {
      onShare({ method: 'copy', status: 'failed', payload });
    }
  };

  const handleSocialClick = (method) => {
    setMenuOpen(false);
    if (typeof onShare === 'function') {
      onShare({ method, status: 'opened', payload });
    }
  };

  return (
    <div
      ref={containerRef}
      dir="rtl"
      className={`share-actions ${className}`.trim()}
    >
      <div className="share-actions__menu-wrapper">
        <button
          type="button"
          className="share-actions__more-btn"
          style={TOUCH_TARGET_STYLE}
          aria-haspopup="menu"
          aria-expanded={menuOpen ? 'true' : 'false'}
          aria-label={`مشاركة "${payload.title}"`}
          data-share-url={payload.url}
          data-whatsapp-url={payload.whatsappUrl}
          onClick={handleTriggerClick}
        >
          <svg
            className="share-actions__icon"
            viewBox="0 0 24 24"
            width="18"
            height="18"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            focusable="false"
          >
            <circle cx="18" cy="5" r="3" />
            <circle cx="6" cy="12" r="3" />
            <circle cx="18" cy="19" r="3" />
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
          </svg>
          <span>{copied ? 'تم النسخ ✓' : 'مشاركة'}</span>
        </button>

        {menuOpen && (
          <div
            className={`share-actions__menu ${
              menuAlign === 'end' ? 'share-actions__menu--align-end' : ''
            }`.trim()}
            role="menu"
            aria-label={`وسائل مشاركة "${payload.title}"`}
          >
            <a
              role="menuitem"
              href={payload.whatsappUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="share-actions__menu-item share-actions__menu-item--whatsapp"
              style={TOUCH_TARGET_STYLE}
              onClick={() => handleSocialClick('whatsapp')}
            >
              <svg
                className="share-actions__icon"
                viewBox="0 0 24 24"
                width="18"
                height="18"
                fill="currentColor"
                aria-hidden="true"
                focusable="false"
              >
                <path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2.05 22l5.25-1.38c1.45.79 3.08 1.21 4.74 1.21 5.46 0 9.91-4.45 9.91-9.91C21.95 6.45 17.5 2 12.04 2zm5.82 14.08c-.24.68-1.42 1.3-1.97 1.38-.52.08-1.18.11-1.91-.12-.44-.14-1.01-.33-1.74-.65-3.06-1.32-5.06-4.41-5.21-4.61-.15-.2-1.24-1.65-1.24-3.15s.79-2.24 1.07-2.54c.28-.3.61-.38.82-.38.2 0 .41.01.59.02.19.01.44-.07.69.53.25.6.85 2.08.93 2.23.08.15.13.33.03.53-.1.2-.15.33-.3.5-.15.18-.32.4-.46.53-.15.15-.31.32-.13.63.18.3.79 1.31 1.7 2.12 1.17 1.04 2.15 1.36 2.46 1.51.3.15.48.13.66-.08.18-.2.76-.88.96-1.18.2-.3.4-.25.68-.15.28.1 1.76.83 2.06.98.3.15.5.23.58.36.08.13.08.76-.16 1.44z" />
              </svg>
              <span>مشاركة عبر واتساب</span>
            </a>

            <a
              role="menuitem"
              href={payload.facebookUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="share-actions__menu-item share-actions__menu-item--facebook"
              style={TOUCH_TARGET_STYLE}
              onClick={() => handleSocialClick('facebook')}
            >
              <svg
                className="share-actions__icon"
                viewBox="0 0 24 24"
                width="18"
                height="18"
                fill="currentColor"
                aria-hidden="true"
                focusable="false"
              >
                <path d="M22 12c0-5.52-4.48-10-10-10S2 6.48 2 12c0 4.84 3.44 8.87 8 9.8V15H8v-3h2V9.5C10 7.57 11.57 6 13.5 6H16v3h-2c-.55 0-1 .45-1 1v2h3v3h-3v6.95c5.05-.5 9-4.76 9-9.95z" />
              </svg>
              <span>مشاركة عبر فيسبوك</span>
            </a>

            <button
              type="button"
              role="menuitem"
              className={`share-actions__menu-item share-actions__menu-item--copy ${
                copied ? 'share-actions__menu-item--copied' : ''
              }`.trim()}
              style={TOUCH_TARGET_STYLE}
              onClick={handleCopyLink}
            >
              <svg
                className="share-actions__icon"
                viewBox="0 0 24 24"
                width="18"
                height="18"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
                focusable="false"
              >
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
              <span>{copied ? 'تم نسخ الرابط ✓' : 'نسخ الرابط'}</span>
            </button>
          </div>
        )}
      </div>

      <span className="sr-only" role="status" aria-live="polite">
        {copied ? 'تم نسخ الرابط بنجاح' : ''}
      </span>
    </div>
  );
}
