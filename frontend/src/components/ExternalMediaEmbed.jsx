import React from 'react';
import {
  MEDIA_TYPE_LABELS,
  resolveExternalMediaEmbed,
} from '../utils/mediaEmbeds.js';
import LazyMediaImage from './LazyMediaImage.jsx';

function extractDisplayHost(urlStr) {
  try {
    return new URL(urlStr).hostname.replace(/^www\./i, '');
  } catch {
    return '';
  }
}

export default function ExternalMediaEmbed({
  media,
  title = '',
  className = '',
}) {
  const resolved = resolveExternalMediaEmbed(media);
  if (!resolved) return null;

  const typeLabel = MEDIA_TYPE_LABELS[resolved.mediaType] || 'وسائط';
  const explicitTitle = typeof title === 'string' ? title.trim() : '';
  const frameTitle =
    explicitTitle ||
    resolved.title ||
    `${typeLabel} - ${resolved.providerLabel}`;

  const badgeLabel = `${typeLabel} • ${resolved.providerLabel}`;
  const isVideoLike =
    resolved.mediaType === 'video' || resolved.mediaType === 'reel';
  const allowFrameScroll =
    resolved.mediaType === 'post' && resolved.provider !== 'canva';
  const renderMode = resolved.renderMode || (resolved.embedUrl ? 'iframe' : 'card');

  const touchTargetStyle = {
    minHeight: '44px',
    minWidth: '44px',
  };

  let orientation = null;
  let frameWrapperStyle;
  if (renderMode === 'iframe' && isVideoLike) {
    const defaultW = resolved.mediaType === 'reel' ? 9 : 16;
    const defaultH = resolved.mediaType === 'reel' ? 16 : 9;
    const aw =
      typeof resolved.aspectWidth === 'number' && resolved.aspectWidth > 0
        ? resolved.aspectWidth
        : defaultW;
    const ah =
      typeof resolved.aspectHeight === 'number' && resolved.aspectHeight > 0
        ? resolved.aspectHeight
        : defaultH;

    const ratio = aw / ah;
    if (ah > aw) {
      orientation = 'portrait';
      frameWrapperStyle = {
        aspectRatio: `${aw} / ${ah}`,
        maxWidth: `min(100%, calc(78vh * ${aw} / ${ah}))`,
      };
    } else if (Math.abs(ratio - 1) < 0.12) {
      orientation = 'square';
      frameWrapperStyle = {
        aspectRatio: `${aw} / ${ah}`,
        maxWidth: 'min(100%, 78vh)',
      };
    } else {
      orientation = 'landscape';
      frameWrapperStyle = {
        aspectRatio: `${aw} / ${ah}`,
        maxWidth: '100%',
      };
    }
  }

  const figureClassName = [
    'media-embed',
    `media-embed--${resolved.mediaType}`,
    `media-embed--${resolved.provider}`,
    className,
  ]
    .filter(Boolean)
    .join(' ');

  const wrapperClassName = [
    'media-embed__frame-wrapper',
    `media-embed__frame-wrapper--${resolved.mediaType}`,
    `media-embed__frame-wrapper--${resolved.provider}`,
    orientation ? `media-embed__frame-wrapper--${orientation}` : '',
  ]
    .filter(Boolean)
    .join(' ');

  const displayHost = extractDisplayHost(resolved.canonicalUrl);

  return (
    <figure
      dir="rtl"
      className={figureClassName}
      data-provider={resolved.provider}
      data-media-type={resolved.mediaType}
      data-render-mode={renderMode}
    >
      <div className="media-embed__header">
        <span className="media-embed__badge">{badgeLabel}</span>
        <a
          href={resolved.canonicalUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="media-embed__external-link"
          style={touchTargetStyle}
        >
          فتح في نافذة جديدة
        </a>
      </div>

      {renderMode === 'image' ? (
        <div className="media-embed__image-wrapper">
          <LazyMediaImage
            src={resolved.canonicalUrl}
            alt={frameTitle}
            className="media-embed__image"
          />
        </div>
      ) : renderMode === 'card' ? (
        <div className="media-embed__card">
          <p className="media-embed__card-title">
            {explicitTitle ||
              resolved.title ||
              `محتوى خارجي (${typeLabel}) عبر ${resolved.providerLabel}`}
          </p>
          {displayHost && (
            <p className="media-embed__card-host">
              <bdi dir="ltr">{displayHost}</bdi>
            </p>
          )}
          <a
            href={resolved.canonicalUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="media-embed__card-cta"
            style={touchTargetStyle}
          >
            فتح {typeLabel} في {resolved.providerLabel}
          </a>
        </div>
      ) : (
        <div
          className={wrapperClassName}
          data-orientation={orientation || undefined}
          style={frameWrapperStyle}
        >
          <iframe
            src={resolved.embedUrl}
            title={frameTitle}
            loading="lazy"
            scrolling={allowFrameScroll ? 'auto' : 'no'}
            referrerPolicy="strict-origin-when-cross-origin"
            sandbox="allow-scripts allow-same-origin allow-presentation allow-popups allow-popups-to-escape-sandbox"
            allow={
              isVideoLike
                ? 'autoplay; clipboard-write; accelerometer; encrypted-media; gyroscope; picture-in-picture; web-share; fullscreen'
                : 'clipboard-write; encrypted-media; web-share'
            }
            allowFullScreen={isVideoLike}
            className="media-embed__iframe"
          />
        </div>
      )}
    </figure>
  );
}
