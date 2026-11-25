import React from 'react';
import { API_BASE_URL, resolveMediaUrl } from '../utils/apiConfig.js';
import { sanitizeImageUrl } from '../utils/mediaEmbeds.js';

export default function LazyMediaImage({
  src,
  alt = '',
  className = '',
  figureClassName = '',
  caption = '',
  width,
  height,
  apiBaseUrl = API_BASE_URL,
}) {
  const safeSrc = sanitizeImageUrl(src);
  if (!safeSrc) return null;
  const resolvedSrc = resolveMediaUrl(safeSrc, apiBaseUrl);

  const trimmedCaption = typeof caption === 'string' ? caption.trim() : '';
  const imgClassName = ['lazy-media-image__img', className]
    .filter(Boolean)
    .join(' ');

  const imgElement = (
    <img
      src={resolvedSrc}
      alt={alt}
      loading="lazy"
      decoding="async"
      className={imgClassName}
      width={width}
      height={height}
    />
  );

  if (!trimmedCaption) {
    return imgElement;
  }

  const wrapperClassName = ['lazy-media-image__figure', figureClassName]
    .filter(Boolean)
    .join(' ');

  return (
    <figure dir="rtl" className={wrapperClassName}>
      {imgElement}
      <figcaption className="lazy-media-image__caption">
        {trimmedCaption}
      </figcaption>
    </figure>
  );
}
