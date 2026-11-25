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

test('AnnouncementsFeed keeps feed cards lightweight (no iframes) and renders allowlisted embed players inside PostDetailView when selected', () => {
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
  ];

  const feedHtml = renderToStaticMarkup(<AnnouncementsFeed posts={posts} />);
  assert.doesNotMatch(
    feedHtml,
    /<iframe/,
    'Feed overview must NOT mount heavy iframe players directly inside list cards'
  );
  assert.match(feedHtml, /<img[^>]+loading="lazy"/, 'Card image must be lazy-loaded');
  assert.ok(feedHtml.includes('فيديو'), 'Card should display lightweight video indicator');
  assert.ok(feedHtml.includes('صوت'), 'Card should display lightweight audio indicator');
  assert.ok(feedHtml.includes('عرض التفاصيل'), 'Card should provide detail view trigger');
  assert.match(feedHtml, /min-height:\s*44px/);
  assert.match(feedHtml, /min-width:\s*44px/);

  const selectedHtml = renderToStaticMarkup(
    <AnnouncementsFeed posts={posts} initialSelectedPostId={77} />
  );
  assert.ok(selectedHtml.includes('حفل تكريم المتفوقين'));
  assert.ok(
    selectedHtml.includes('يتضمن الحفل كلمة اللجنة وعرضاً مرئياً وتسجيلاً صوتياً للنشيد المدرسي.')
  );
  assert.match(selectedHtml, /<iframe[^>]+youtube-nocookie\.com\/embed\/dQw4w9WgXcQ/);
  assert.match(selectedHtml, /<iframe[^>]+w\.soundcloud\.com\/player\/\?url=/);
  assert.ok(selectedHtml.includes('العودة إلى قائمة الإعلانات'));
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
