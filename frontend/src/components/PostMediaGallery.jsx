import React from 'react';
import { extractPostMedia } from '../utils/mediaEmbeds.js';
import ExternalMediaEmbed from './ExternalMediaEmbed.jsx';
import LazyMediaImage from './LazyMediaImage.jsx';

export default function PostMediaGallery({ post, excludeImageUrls = [] }) {
  const { images, embeds } = extractPostMedia(post);
  const excludedSet = new Set(
    (Array.isArray(excludeImageUrls) ? excludeImageUrls : [])
      .filter((u) => typeof u === 'string' && u.trim())
      .map((u) => u.trim())
  );
  const visibleImages =
    excludedSet.size > 0
      ? images.filter((image) => !excludedSet.has(image.url))
      : images;

  if (visibleImages.length === 0 && embeds.length === 0) {
    return null;
  }

  return (
    <div
      dir="rtl"
      className="post-media-gallery"
      aria-label="الوسائط المرفقة"
    >
      {visibleImages.length > 0 && (
        <div className="post-media-gallery__images">
          {visibleImages.map((image) => (
            <LazyMediaImage
              key={image.url}
              src={image.url}
              alt={image.alt}
              caption={image.caption}
              width={image.width}
              height={image.height}
              className="post-media-gallery__image"
            />
          ))}
        </div>
      )}

      {embeds.length > 0 && (
        <div className="post-media-gallery__embeds">
          {embeds.map((embed) => (
            <ExternalMediaEmbed
              key={embed.embedUrl || embed.canonicalUrl}
              media={embed}
            />
          ))}
        </div>
      )}
    </div>
  );
}
