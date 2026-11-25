import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  RAW_AV_EXTENSIONS,
  extractPostMedia,
  resolveExternalMediaEmbed,
  sanitizeImageUrl,
} from '../utils/mediaEmbeds.js';
import LazyMediaImage from '../components/LazyMediaImage.jsx';
import ExternalMediaEmbed from '../components/ExternalMediaEmbed.jsx';
import PostMediaGallery from '../components/PostMediaGallery.jsx';
import PostDetailView from '../components/PostDetailView.jsx';
import AnnouncementsFeed from '../components/AnnouncementsFeed.jsx';

function collectFilesRecursively(dir) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...collectFilesRecursively(fullPath));
    } else {
      results.push(fullPath);
    }
  }
  return results;
}

test('sanitizeImageUrl accepts HTTPS URLs and safe root-relative paths while rejecting unsafe or raw A/V URLs', () => {
  assert.equal(
    sanitizeImageUrl('  https://example.com/posts/heritage-day.webp  '),
    'https://example.com/posts/heritage-day.webp'
  );
  assert.equal(
    sanitizeImageUrl('/api/media/images/0123456789abcdef.webp'),
    '/api/media/images/0123456789abcdef.webp'
  );
  assert.equal(sanitizeImageUrl('/logo.jpg'), '/logo.jpg');

  const rejectedInputs = [
    '',
    '   ',
    null,
    undefined,
    'http://example.com/photo.webp',
    'javascript:alert(1)',
    'data:image/svg+xml,<svg onload="alert(1)"/>',
    '//evil.com/a.webp',
    '/api/../secret.webp',
    'https://user:pass@example.com/a.webp',
    'https://example.com/icon.svg',
    '/assets/badge.svg?v=1',
    'https://example.com/clip.mp4',
    'https://example.com/audio.mp3',
    '/media/sound.wav',
    'https://example.com/video.webm',
    'https://example.com/video.mov',
    'https://example.com/audio.ogg',
    'https://example.com/audio.m4a',
  ];

  for (const bad of rejectedInputs) {
    assert.equal(
      sanitizeImageUrl(bad),
      null,
      `Expected sanitizeImageUrl(${String(bad)}) to return null`
    );
  }
});

test('resolveExternalMediaEmbed normalizes allowlisted video and audio URLs to HTTPS embed URLs', () => {
  const youtubeUrls = [
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share',
    'https://youtu.be/dQw4w9WgXcQ?t=15',
    'https://m.youtube.com/watch?v=dQw4w9WgXcQ',
    'https://www.youtube.com/shorts/dQw4w9WgXcQ',
    'https://www.youtube.com/live/dQw4w9WgXcQ',
    'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ',
  ];

  for (const url of youtubeUrls) {
    const resolved = resolveExternalMediaEmbed(url);
    assert.ok(resolved, `Should resolve YouTube URL: ${url}`);
    assert.equal(resolved.mediaType, 'video');
    assert.equal(resolved.provider, 'youtube');
    assert.equal(
      resolved.embedUrl,
      'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ'
    );
    assert.equal(resolved.hostedExternally, true);
  }

  for (const vimeoUrl of [
    'https://vimeo.com/123456789',
    'https://player.vimeo.com/video/123456789',
  ]) {
    const resolved = resolveExternalMediaEmbed(vimeoUrl);
    assert.ok(resolved, `Should resolve Vimeo URL: ${vimeoUrl}`);
    assert.equal(resolved.mediaType, 'video');
    assert.equal(resolved.provider, 'vimeo');
    assert.equal(resolved.embedUrl, 'https://player.vimeo.com/video/123456789');
    assert.equal(resolved.hostedExternally, true);
  }

  const scUrls = [
    'https://soundcloud.com/school/morning-announcement',
    'https://w.soundcloud.com/player/?url=https%3A%2F%2Fsoundcloud.com%2Fschool%2Fmorning-announcement',
  ];
  for (const scUrl of scUrls) {
    const resolved = resolveExternalMediaEmbed(scUrl);
    assert.ok(resolved, `Should resolve SoundCloud URL: ${scUrl}`);
    assert.equal(resolved.mediaType, 'audio');
    assert.equal(resolved.provider, 'soundcloud');
    assert.ok(
      resolved.embedUrl.startsWith('https://w.soundcloud.com/player/?url='),
      'SoundCloud embedUrl must use official player endpoint'
    );
    assert.ok(
      resolved.embedUrl.includes('auto_play=false'),
      'SoundCloud embedUrl should disable autoplay'
    );
    assert.equal(resolved.hostedExternally, true);
  }

  const driveUrls = [
    'https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/view?usp=sharing',
    'https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQr',
    'https://drive.google.com/uc?id=1AbCdEfGhIjKlMnOpQr',
  ];
  for (const driveUrl of driveUrls) {
    const resolved = resolveExternalMediaEmbed(driveUrl);
    assert.ok(resolved, `Should resolve Google Drive URL: ${driveUrl}`);
    assert.equal(resolved.mediaType, 'audio');
    assert.equal(resolved.provider, 'google_drive');
    assert.equal(
      resolved.embedUrl,
      'https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/preview'
    );
    assert.equal(resolved.hostedExternally, true);
  }
});

test('resolveExternalMediaEmbed rejects untrusted domains, non-HTTPS, credentials, local files, and mediaType mismatches', () => {
  const rejected = [
    ['http://www.youtube.com/watch?v=dQw4w9WgXcQ', null],
    ['javascript:alert(1)', null],
    ['https://evil.example.com/video.mp4', null],
    ['https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ', null],
    ['https://user:pass@youtube.com/watch?v=dQw4w9WgXcQ', null],
    ['https://w.soundcloud.com/player/?url=https://evil.com/track', null],
    ['/media/local.mp4', null],
    [{ url: 'https://soundcloud.com/school/track', mediaType: 'video' }, null],
    ['https://soundcloud.com/school/track', 'video'],
  ];

  for (const [input, explicitType] of rejected) {
    assert.equal(
      resolveExternalMediaEmbed(input, explicitType),
      null,
      `Expected rejection for ${JSON.stringify(input)}`
    );
  }
});

test('extractPostMedia extracts deduplicated safe images and allowlisted external embeds', () => {
  const post = {
    id: 1,
    title: 'فعالية يوم التراث',
    imageUrl: 'https://example.com/posts/main.webp',
    images: [
      'https://example.com/posts/main.webp',
      { url: '/api/media/images/abcdef0123456789.webp', caption: 'صورة من الساحة' },
      'javascript:alert(1)',
      'https://example.com/bad.svg',
    ],
    mediaLinks: [
      'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
      'https://youtu.be/dQw4w9WgXcQ',
      { url: 'https://evil.com/video.mp4', mediaType: 'video' },
    ],
    videoUrl: 'https://vimeo.com/123456789',
    audioUrl: 'https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/view',
  };

  const { images, embeds } = extractPostMedia(post);
  assert.equal(images.length, 2, 'Should deduplicate and drop unsafe images');
  assert.equal(images[0].url, 'https://example.com/posts/main.webp');
  assert.equal(images[1].url, '/api/media/images/abcdef0123456789.webp');
  assert.equal(images[1].caption, 'صورة من الساحة');

  assert.equal(embeds.length, 3, 'Should deduplicate YouTube and keep Vimeo + Drive audio');
  assert.deepEqual(
    embeds.map((e) => e.provider),
    ['youtube', 'vimeo', 'google_drive']
  );
});

test('LazyMediaImage renders lazy-loaded image, optional figcaption, and rejects unsafe sources', () => {
  const html = renderToStaticMarkup(
    <LazyMediaImage
      src="https://example.com/posts/event.webp"
      alt="صورة الفعالية"
      caption="جانب من المشاركة الطلابية"
    />
  );

  assert.match(html, /<img[^>]+loading="lazy"/, 'Image must include loading="lazy"');
  assert.match(html, /<img[^>]+decoding="async"/, 'Image should include decoding="async"');
  assert.match(
    html,
    /<img[^>]+src="https:\/\/example\.com\/posts\/event\.webp"/,
    'Image must render sanitized src'
  );
  assert.match(html, /<img[^>]+alt="صورة الفعالية"/, 'Image must render alt text');
  assert.ok(html.includes('<figure'), 'Caption should wrap image in <figure>');
  assert.ok(
    html.includes('<figcaption') && html.includes('جانب من المشاركة الطلابية'),
    'Should render figcaption text'
  );

  for (const unsafe of [
    '',
    'javascript:alert(1)',
    'http://example.com/a.webp',
    'https://example.com/a.svg',
    'https://example.com/a.mp4',
  ]) {
    const emptyHtml = renderToStaticMarkup(<LazyMediaImage src={unsafe} alt="bad" />);
    assert.equal(emptyHtml, '', `Unsafe src (${unsafe}) must render empty markup`);
  }
});

test('ExternalMediaEmbed renders allowlisted lazy-loaded iframe players and accessible fallback links while rejecting untrusted media', () => {
  const sources = [
    {
      url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
      expectedIframeSrc: 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ',
    },
    {
      url: 'https://vimeo.com/123456789',
      expectedIframeSrc: 'https://player.vimeo.com/video/123456789',
    },
    {
      url: 'https://soundcloud.com/school/morning-announcement',
      expectedIframeSrc: 'https://w.soundcloud.com/player/?url=',
    },
    {
      url: 'https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/view',
      expectedIframeSrc: 'https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/preview',
    },
  ];

  for (const { url, expectedIframeSrc } of sources) {
    const html = renderToStaticMarkup(<ExternalMediaEmbed media={url} />);
    assert.match(html, /<figure[^>]+dir="rtl"/, 'Embed wrapper must enforce RTL');
    assert.match(html, /<iframe\b/, 'Should render iframe player');
    assert.match(html, /loading="lazy"/, 'Iframe player must use loading="lazy"');
    assert.match(
      html,
      /referrerpolicy="strict-origin-when-cross-origin"/i,
      'Iframe must enforce strict referrer policy'
    );
    assert.match(html, /sandbox="/, 'Iframe must apply sandbox restrictions');
    assert.match(html, /title="[^"]+"/, 'Iframe must include accessible title');
    assert.ok(
      html.includes(expectedIframeSrc),
      `Iframe src must normalize to ${expectedIframeSrc}`
    );
    assert.match(
      html,
      /<a[^>]+target="_blank"[^>]+rel="noopener noreferrer"/,
      'Should include safe external fallback link'
    );
    assert.match(html, /min-height:\s*44px/, 'Fallback link must meet 44px touch height');
    assert.match(html, /min-width:\s*44px/, 'Fallback link must meet 44px touch width');
  }

  for (const bad of [
    'https://evil.example.com/video.mp4',
    'https://cdn.example.com/audio.mp3',
    'javascript:alert(1)',
  ]) {
    const badHtml = renderToStaticMarkup(<ExternalMediaEmbed media={bad} />);
    assert.equal(badHtml, '', `Untrusted media (${bad}) must render nothing`);
    assert.doesNotMatch(badHtml, /<iframe|<video|<audio/);
  }
});

test('PostDetailView and PostMediaGallery render RTL detail view with lazy images, allowlisted embeds, and accessible back button', () => {
  const post = {
    id: 501,
    title: 'تغطية يوم الرياضة المدرسي',
    summary: 'ملخص قصير',
    content: 'تفاصيل كاملة لليوم الرياضي بمشاركة الأهالي والطلاب.',
    category: 'student_activity',
    publishedAt: '2026-11-24T10:00:00Z',
    eventDate: '2026-12-10',
    imageUrl: '/api/media/images/0123456789abcdef.webp',
    mediaLinks: [
      'https://youtu.be/dQw4w9WgXcQ',
      'https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQr/view',
      'https://untrusted.example.com/heavy.mp4',
    ],
  };

  const galleryHtml = renderToStaticMarkup(<PostMediaGallery post={post} />);
  assert.match(galleryHtml, /<img[^>]+loading="lazy"/);
  assert.match(galleryHtml, /youtube-nocookie\.com\/embed\/dQw4w9WgXcQ/);
  assert.match(galleryHtml, /drive\.google\.com\/file\/d\/1AbCdEfGhIjKlMnOpQr\/preview/);
  assert.ok(!galleryHtml.includes('untrusted.example.com'));
  assert.doesNotMatch(galleryHtml, /<video|<audio/);

  const detailHtml = renderToStaticMarkup(
    <PostDetailView post={post} onClose={() => {}} />
  );
  assert.match(detailHtml, /dir="rtl"/, 'PostDetailView must enforce RTL');
  assert.ok(detailHtml.includes('تغطية يوم الرياضة المدرسي'));
  assert.ok(detailHtml.includes('تفاصيل كاملة لليوم الرياضي بمشاركة الأهالي والطلاب.'));
  assert.ok(detailHtml.includes('نشاط طلابي'));
  assert.ok(detailHtml.includes('موعد الفعالية:'));
  assert.match(detailHtml, /<img[^>]+loading="lazy"/);
  assert.match(detailHtml, /<iframe[^>]+loading="lazy"/);
  assert.ok(detailHtml.includes('العودة إلى قائمة الإعلانات'));
  assert.match(detailHtml, /min-height:\s*44px/);
  assert.match(detailHtml, /min-width:\s*44px/);
});

test('AnnouncementsFeed renders posts stacked vertically with full content and lazy-loaded embeds inline (no detail toggle)', () => {
  const posts = [
    {
      id: 77,
      title: 'حفل تكريم المتفوقين',
      summary: 'دعوة لأهالي الطلاب لحضور الحفل السنوي.',
      content: 'يتضمن الحفل كلمة اللجنة وعرضاً مرئياً وتسجيلاً صوتياً للنشيد المدرسي.',
      category: 'upcoming_event',
      publishedAt: '2026-11-25T10:00:00Z',
      imageUrl: 'https://example.com/posts/ceremony.webp',
      mediaLinks: [
        'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        'https://soundcloud.com/school/anthem',
      ],
    },
    {
      id: 78,
      title: 'فعالية ثانية في الأسفل',
      summary: 'ملخص الفعالية الثانية.',
      category: 'general',
      publishedAt: '2026-11-24T10:00:00Z',
    },
  ];

  const feedHtml = renderToStaticMarkup(<AnnouncementsFeed posts={posts} />);
  assert.match(feedHtml, /<img[^>]+loading="lazy"/, 'Card image must be lazy-loaded');
  assert.ok(feedHtml.includes('فيديو'), 'Card should display video indicator');
  assert.ok(feedHtml.includes('صوت'), 'Card should display audio indicator');
  assert.ok(feedHtml.includes('حفل تكريم المتفوقين'));
  assert.ok(feedHtml.includes('فعالية ثانية في الأسفل'));
  assert.ok(
    feedHtml.includes('يتضمن الحفل كلمة اللجنة وعرضاً مرئياً وتسجيلاً صوتياً للنشيد المدرسي.')
  );
  assert.match(feedHtml, /<iframe[^>]+loading="lazy"/, 'Inline embeds must use lazy loading');
  assert.match(feedHtml, /<iframe[^>]+youtube-nocookie\.com\/embed\/dQw4w9WgXcQ/);
  assert.match(feedHtml, /<iframe[^>]+w\.soundcloud\.com\/player\/\?url=/);
  assert.ok(!feedHtml.includes('عرض التفاصيل'), 'Detail toggle button must be omitted');
  assert.ok(!feedHtml.includes('إخفاء التفاصيل'), 'Detail toggle button must be omitted');
  assert.match(feedHtml, /min-height:\s*44px/);
  assert.match(feedHtml, /min-width:\s*44px/);
});

test('ExternalMediaEmbed adapts frame aspect-ratio and orientation to original portrait, square, and landscape media', () => {
  const portraitFbHtml = renderToStaticMarkup(
    <ExternalMediaEmbed
      media={{
        canonicalUrl: 'https://www.facebook.com/watch/?v=987654321',
        mediaType: 'video',
        aspectWidth: 720,
        aspectHeight: 1280,
      }}
    />
  );
  assert.match(portraitFbHtml, /data-orientation="portrait"/);
  assert.match(portraitFbHtml, /aspect-ratio:\s*720\s*\/\s*1280/);
  assert.match(portraitFbHtml, /max-width:\s*min\(100%,\s*calc\(78vh \* 720 \/ 1280\)\)/);

  const ytShortsHtml = renderToStaticMarkup(
    <ExternalMediaEmbed media="https://www.youtube.com/shorts/dQw4w9WgXcQ" />
  );
  assert.match(ytShortsHtml, /data-orientation="portrait"/);
  assert.match(ytShortsHtml, /aspect-ratio:\s*9\s*\/\s*16/);

  const squareFbHtml = renderToStaticMarkup(
    <ExternalMediaEmbed
      media={{
        canonicalUrl: 'https://www.facebook.com/watch/?v=111222333',
        mediaType: 'video',
        aspectWidth: 1080,
        aspectHeight: 1080,
      }}
    />
  );
  assert.match(squareFbHtml, /data-orientation="square"/);
  assert.match(squareFbHtml, /aspect-ratio:\s*1080\s*\/\s*1080/);

  const landscapeHtml = renderToStaticMarkup(
    <ExternalMediaEmbed media="https://www.youtube.com/watch?v=dQw4w9WgXcQ" />
  );
  assert.match(landscapeHtml, /data-orientation="landscape"/);
  assert.match(landscapeHtml, /aspect-ratio:\s*16\s*\/\s*9/);

  const landscapeReelHtml = renderToStaticMarkup(
    <ExternalMediaEmbed
      media={{
        canonicalUrl: 'https://www.facebook.com/reel/1391452396433188',
        mediaType: 'reel',
        aspectWidth: 1280,
        aspectHeight: 720,
      }}
    />
  );
  assert.match(landscapeReelHtml, /data-orientation="landscape"/);
  assert.match(landscapeReelHtml, /aspect-ratio:\s*1280\s*\/\s*720/);
  assert.match(landscapeReelHtml, /max-width:\s*100%/);
});

test('resolveExternalMediaEmbed and ExternalMediaEmbed support social reels, posts, external images, and audio across iframe, image, and card render modes', () => {
  const cases = [
    {
      input: 'https://www.instagram.com/reel/C5AbCdEfGhI/',
      mediaType: 'reel',
      provider: 'instagram',
      renderMode: 'iframe',
      expectedEmbed: 'https://www.instagram.com/reel/C5AbCdEfGhI/embed/',
    },
    {
      input: 'https://www.facebook.com/reel/123456789012345',
      mediaType: 'reel',
      provider: 'facebook',
      renderMode: 'iframe',
      expectedEmbed: 'https://www.facebook.com/plugins/video.php?href=',
    },
    {
      input: 'https://www.facebook.com/mahjar.school/posts/pfbid02XYZ123',
      mediaType: 'post',
      provider: 'facebook',
      renderMode: 'iframe',
      expectedEmbed: 'https://www.facebook.com/plugins/post.php?href=',
    },
    {
      input: 'https://www.facebook.com/share/v/19kinDFpk5/',
      mediaType: 'video',
      provider: 'facebook',
      renderMode: 'card',
      expectedEmbed: '',
    },
    {
      input: {
        canonicalUrl: 'https://www.facebook.com/watch/?v=987654321',
        originalUrl: 'https://www.facebook.com/share/v/19kinDFpk5/',
      },
      mediaType: 'video',
      provider: 'facebook',
      renderMode: 'iframe',
      expectedEmbed: 'https://www.facebook.com/plugins/video.php?href=',
    },
    {
      input: 'https://www.tiktok.com/@mahjarschool/video/7345678901234567890',
      mediaType: 'reel',
      provider: 'tiktok',
      renderMode: 'iframe',
      expectedEmbed: 'https://www.tiktok.com/embed/v2/7345678901234567890',
    },
    {
      input: 'https://open.spotify.com/episode/4rOoJ6Egrf8K2IrywzwOMk',
      mediaType: 'audio',
      provider: 'spotify',
      renderMode: 'iframe',
      expectedEmbed: 'https://open.spotify.com/embed/episode/4rOoJ6Egrf8K2IrywzwOMk',
    },
    {
      input: 'https://www.dailymotion.com/video/x8abcde',
      mediaType: 'video',
      provider: 'dailymotion',
      renderMode: 'iframe',
      expectedEmbed: 'https://www.dailymotion.com/embed/video/x8abcde',
    },
    {
      input: 'https://www.threads.net/@mahjar.school/post/C9AbCdEf123',
      mediaType: 'post',
      provider: 'threads',
      renderMode: 'iframe',
      expectedEmbed: 'https://www.threads.net/@mahjar.school/post/C9AbCdEf123/embed',
    },
    {
      input: 'https://t.me/mahjar_parents/42',
      mediaType: 'post',
      provider: 'telegram',
      renderMode: 'iframe',
      expectedEmbed: 'https://t.me/mahjar_parents/42?embed=1',
    },
    {
      input: 'https://www.linkedin.com/posts/mahjar-school_activity-12345',
      mediaType: 'post',
      provider: 'linkedin',
      renderMode: 'iframe',
      expectedEmbed: 'https://www.linkedin.com/embed/feed/update/urn:li:activity:12345',
    },
    {
      input: 'https://www.canva.com/design/DAGAbCdEfGh/view',
      mediaType: 'post',
      provider: 'canva',
      renderMode: 'iframe',
      expectedEmbed: 'https://www.canva.com/design/DAGAbCdEfGh/view?embed',
    },
    {
      input: 'https://x.com/mahjar_school/status/1800123456789012345',
      mediaType: 'post',
      provider: 'x',
      renderMode: 'card',
      expectedEmbed: '',
    },
    {
      input: 'https://vm.tiktok.com/ZMrAbCdEf/',
      mediaType: 'reel',
      provider: 'tiktok',
      renderMode: 'card',
      expectedEmbed: '',
    },
    {
      input: 'https://cdn.example.org/gallery/heritage-day.webp',
      mediaType: 'image',
      provider: 'external_image',
      renderMode: 'image',
      expectedEmbed: '',
    },
  ];

  for (const c of cases) {
    const resolved = resolveExternalMediaEmbed(c.input);
    assert.ok(resolved, `Should resolve ${c.input}`);
    assert.equal(resolved.mediaType, c.mediaType);
    assert.equal(resolved.provider, c.provider);
    assert.equal(resolved.renderMode, c.renderMode);

    const html = renderToStaticMarkup(<ExternalMediaEmbed media={c.input} />);
    assert.match(html, new RegExp(`data-render-mode="${c.renderMode}"`));
    assert.match(html, new RegExp(`data-media-type="${c.mediaType}"`));
    if (c.renderMode === 'iframe') {
      assert.match(html, /<iframe\b/);
      assert.ok(html.includes(c.expectedEmbed));
    } else if (c.renderMode === 'image') {
      assert.doesNotMatch(html, /<iframe\b/);
      assert.match(html, /<img[^>]+loading="lazy"/);
    } else {
      assert.doesNotMatch(html, /<iframe\b|<video\b|<audio\b/);
      assert.match(html, /class="media-embed__card"/);
      assert.match(html, /<bdi dir="ltr">/);
      assert.match(html, /min-height:\s*44px/);
    }
  }

  // Deduplicates multiple card/image links without colliding on empty embedUrl
  const { embeds } = extractPostMedia({
    id: 90,
    title: 'تغطية متعددة',
    mediaLinks: [
      { url: 'https://x.com/mahjar_school/status/1800123456789012345', embedUrl: '' },
      { url: 'https://t.me/mahjar_parents/42', embedUrl: '' },
      { url: 'https://cdn.example.org/gallery/photo1.webp', embedUrl: '' },
    ],
  });
  assert.equal(embeds.length, 3);

  // Security rejections for private/local/SVG external images
  assert.equal(resolveExternalMediaEmbed('https://127.0.0.1/a.jpg'), null);
  assert.equal(resolveExternalMediaEmbed('https://localhost/a.png', 'image'), null);
  assert.equal(resolveExternalMediaEmbed('https://cdn.example.org/a.svg', 'image'), null);
});

test('Frontend source and public assets do not bundle heavy raw video or audio files into the hosting tier', () => {
  const srcFiles = collectFilesRecursively(path.resolve(process.cwd(), 'src'));
  const publicFiles = collectFilesRecursively(path.resolve(process.cwd(), 'public'));
  const allAssetFiles = [...srcFiles, ...publicFiles];

  assert.ok(allAssetFiles.length > 0, 'Should locate frontend files to inspect');
  for (const filePath of allAssetFiles) {
    const ext = path.extname(filePath).toLowerCase();
    assert.ok(
      !RAW_AV_EXTENSIONS.has(ext),
      `Raw audio/video file must not be bundled in frontend hosting tier: ${filePath}`
    );
  }
});
