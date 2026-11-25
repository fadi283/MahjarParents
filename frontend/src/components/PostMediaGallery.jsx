import React from 'react';
import { extractPostMedia } from '../utils/mediaEmbeds.js';
import ExternalMediaEmbed from './ExternalMediaEmbed.jsx';
import LazyMediaImage from './LazyMediaImage.jsx';

export default function PostMediaGallery({ post }) {
  const { images, embeds } = extractPostMedia(post);
  if (images.length === 0 && embeds.length === 0) {
    return null;
  }

  return (
    <div
      dir="rtl"
      className="post-media-gallery"
      aria-label="الوسائط المرفقة"
    >
      {images.length > 0 && (
        <div className="post-media-gallery__images">
          {images.map((image) => (
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
              key={embed.embedUrl}
              media={embed}
            />
          ))}
        </div>
      )}
    </div>
  );
}
