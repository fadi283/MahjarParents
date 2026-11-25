import React from 'react';
import {
  buildSharePayload,
  canUseWebShare,
  sharePost,
} from '../utils/whatsappShare.js';

export default function WhatsAppShareButton({
  post,
  entityType = 'post',
  baseUrl,
  className = '',
  label = 'مشاركة عبر واتساب',
  preferWebShare = false,
  onShare,
}) {
  const payload = buildSharePayload(post, { baseUrl, entityType });
  if (!payload) return null;

  const touchTargetStyle = {
    minHeight: '44px',
    minWidth: '44px',
  };

  const handleClick = async (event) => {
    const navigatorObj = typeof navigator !== 'undefined' ? navigator : null;
    const isAbsoluteHttp = /^https?:\/\//i.test(payload.url);
    const webShareData = isAbsoluteHttp
      ? { title: payload.title, text: payload.title, url: payload.url }
      : { title: payload.title, text: payload.text };

    if (preferWebShare && canUseWebShare(navigatorObj, webShareData)) {
      event.preventDefault();
      const result = await sharePost(post, {
        baseUrl,
        entityType,
        preferWebShare: true,
      });
      if (typeof onShare === 'function') {
        onShare(result);
      }
      return;
    }

    if (typeof onShare === 'function') {
      onShare({ method: 'whatsapp', status: 'opened', payload });
    }
  };

  return (
    <a
      dir="rtl"
      href={payload.whatsappUrl}
      target="_blank"
      rel="noopener noreferrer"
      className={`whatsapp-share-btn ${className}`.trim()}
      style={touchTargetStyle}
      aria-label={`مشاركة "${payload.title}" عبر واتساب`}
      data-share-url={payload.url}
      onClick={handleClick}
    >
      <svg
        className="whatsapp-share-btn__icon"
        viewBox="0 0 24 24"
        width="18"
        height="18"
        fill="currentColor"
        aria-hidden="true"
        focusable="false"
      >
        <path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2.05 22l5.25-1.38c1.45.79 3.08 1.21 4.74 1.21 5.46 0 9.91-4.45 9.91-9.91C21.95 6.45 17.5 2 12.04 2zm5.82 14.08c-.24.68-1.42 1.3-1.97 1.38-.52.08-1.18.11-1.91-.12-.44-.14-1.01-.33-1.74-.65-3.06-1.32-5.06-4.41-5.21-4.61-.15-.2-1.24-1.65-1.24-3.15s.79-2.24 1.07-2.54c.28-.3.61-.38.82-.38.2 0 .41.01.59.02.19.01.44-.07.69.53.25.6.85 2.08.93 2.23.08.15.13.33.03.53-.1.2-.15.33-.3.5-.15.18-.32.4-.46.53-.15.15-.31.32-.13.63.18.3.79 1.31 1.7 2.12 1.17 1.04 2.15 1.36 2.46 1.51.3.15.48.13.66-.08.18-.2.76-.88.96-1.18.2-.3.4-.25.68-.15.28.1 1.76.83 2.06.98.3.15.5.23.58.36.08.13.08.76-.16 1.44z" />
      </svg>
      <span>{label}</span>
    </a>
  );
}
