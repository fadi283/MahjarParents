import React, { useEffect, useState } from 'react';
import {
  ENGAGEMENT_FORM_META,
  normalizeEngagementForm,
} from '../utils/engagementForms.js';
import ShareActions from './ShareActions.jsx';

const TOUCH_TARGET_STYLE = {
  minHeight: '44px',
  minWidth: '44px',
};

export default function GoogleFormEmbed({ form, className = '', shareBaseUrl }) {
  const resolved = normalizeEngagementForm(form);
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    setIsLoaded(false);
  }, [resolved?.embedUrl]);

  if (!resolved) return null;

  const meta = ENGAGEMENT_FORM_META[resolved.formType] ?? {
    label: resolved.formType,
    badge: resolved.formType,
  };

  const wrapperClassName = [
    'engagement-embed',
    `engagement-embed--${resolved.formType}`,
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div
      dir="rtl"
      className={wrapperClassName}
      data-form-id={String(resolved.id)}
      data-form-type={resolved.formType}
    >
      <div className="engagement-embed__header">
        <div className="engagement-embed__heading-group">
          <span
            className={`engagement-card__badge engagement-card__badge--${resolved.formType}`}
          >
            {meta.badge}
          </span>
          <h3 className="engagement-embed__title">{resolved.title}</h3>
          {resolved.description && (
            <p className="engagement-embed__description">{resolved.description}</p>
          )}
        </div>

        <div className="engagement-embed__header-actions">
          <ShareActions
            item={resolved}
            entityType="form"
            baseUrl={shareBaseUrl}
          />
          <a
            href={resolved.directUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="engagement-embed__direct-link"
            style={TOUCH_TARGET_STYLE}
          >
            فتح النموذج في نافذة جديدة
          </a>
        </div>
      </div>

      <div className="engagement-embed__frame-wrapper">
        {!isLoaded && (
          <p className="engagement-embed__loading" aria-live="polite">
            يتم تحميل النموذج المضمّن... يمكنك أيضاً استخدام الرابط المباشر أدناه في أي وقت.
          </p>
        )}
        <iframe
          loading="lazy"
          src={resolved.embedUrl}
          title={resolved.title}
          referrerPolicy="strict-origin-when-cross-origin"
          sandbox="allow-scripts allow-forms allow-same-origin allow-popups allow-popups-to-escape-sandbox"
          className="engagement-embed__iframe"
          onLoad={() => setIsLoaded(true)}
        />
      </div>

      <div className="engagement-embed__footer">
        <p className="engagement-embed__fallback-note">
          في حال عدم ظهور النموذج داخل الصفحة على هاتفك أو متصفحك، افتحه مباشرة عبر Google Forms:
        </p>
        <a
          href={resolved.directUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="engagement-embed__fallback-btn"
          style={TOUCH_TARGET_STYLE}
        >
          الانتقال المباشر للنموذج
        </a>
      </div>
    </div>
  );
}
