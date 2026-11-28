import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import {
  buildApiUrl,
  normalizeApiBaseUrl,
  resolveApiBaseUrl,
  resolveMediaUrl,
} from '../../utils/apiConfig.js';
import { createAdminApiClient } from '../../utils/adminApi.js';
import { fetchPublicEngagementForms } from '../../utils/engagementForms.js';
import LazyMediaImage from '../../components/LazyMediaImage.jsx';
import CommitteeMemberCard from '../../components/CommitteeMemberCard.jsx';
import { verifyDistDirectory } from '../../../scripts/verify-dist.js';

test('apiConfig normalizes HTTPS and localhost origins and rejects unsafe or remote HTTP origins', () => {
  assert.equal(
    normalizeApiBaseUrl('https://api.mahjar.onrender.com/'),
    'https://api.mahjar.onrender.com'
  );
  assert.equal(
    normalizeApiBaseUrl('http://localhost:5000/'),
    'http://localhost:5000'
  );
  assert.equal(
    normalizeApiBaseUrl('http://127.0.0.1:5000'),
    'http://127.0.0.1:5000'
  );
  assert.equal(normalizeApiBaseUrl('http://insecure.example.com'), '');
  assert.equal(normalizeApiBaseUrl('javascript:alert(1)'), '');
  assert.equal(normalizeApiBaseUrl('https://user:pass@api.example.com'), '');
  assert.equal(normalizeApiBaseUrl('not a url'), '');

  assert.equal(
    resolveApiBaseUrl({ VITE_API_BASE_URL: 'https://mahjar-api.onrender.com///' }),
    'https://mahjar-api.onrender.com'
  );
  assert.equal(resolveApiBaseUrl({}), '');
});

test('buildApiUrl and resolveMediaUrl resolve split-origin API and OpenCV media paths safely', () => {
  assert.equal(buildApiUrl('/api/posts', ''), '/api/posts');
  assert.equal(
    buildApiUrl('/api/posts', 'https://api.mahjar.onrender.com/'),
    'https://api.mahjar.onrender.com/api/posts'
  );

  assert.equal(
    resolveMediaUrl('/api/media/images/0123456789abcdef.webp', 'https://api.mahjar.onrender.com'),
    'https://api.mahjar.onrender.com/api/media/images/0123456789abcdef.webp'
  );
  assert.equal(
    resolveMediaUrl('/logo.jpg', 'https://api.mahjar.onrender.com'),
    '/logo.jpg'
  );
  assert.equal(
    resolveMediaUrl('https://cdn.example.com/photo.webp', 'https://api.mahjar.onrender.com'),
    'https://cdn.example.com/photo.webp'
  );
});

test('adminApi and fetchPublicEngagementForms honor normalized split-origin baseUrl', async () => {
  const calls = [];
  const mockFetch = async (url, options) => {
    calls.push({ url, options });
    return {
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => [],
    };
  };

  const api = createAdminApiClient({
    fetchImpl: mockFetch,
    storage: null,
    baseUrl: 'https://api.mahjar.onrender.com/',
  });
  await api.listPosts();
  assert.equal(calls[0].url, 'https://api.mahjar.onrender.com/api/admin/posts');

  await fetchPublicEngagementForms(mockFetch, {
    formType: 'feedback',
    baseUrl: 'https://api.mahjar.onrender.com/',
  });
  assert.equal(
    calls[1].url,
    'https://api.mahjar.onrender.com/api/forms?type=feedback'
  );
});

test('LazyMediaImage and CommitteeMemberCard prefix /api/media/images paths when apiBaseUrl is provided', () => {
  const mediaHtml = renderToStaticMarkup(
    <LazyMediaImage
      src="/api/media/images/0123456789abcdef.webp"
      alt="صورة محسنة"
      apiBaseUrl="https://api.mahjar.onrender.com"
    />
  );
  assert.match(
    mediaHtml,
    /src="https:\/\/api\.mahjar\.onrender\.com\/api\/media\/images\/0123456789abcdef\.webp"/
  );
  assert.match(mediaHtml, /loading="lazy"/);

  const memberHtml = renderToStaticMarkup(
    <CommitteeMemberCard
      apiBaseUrl="https://api.mahjar.onrender.com"
      member={{
        id: 1,
        fullName: 'أحمد علي',
        role: 'عضو لجنة',
        responsibilitySummary: 'التنسيق',
        avatarUrl: '/api/media/images/abcdef0123456789.webp',
      }}
    />
  );
  assert.match(
    memberHtml,
    /src="https:\/\/api\.mahjar\.onrender\.com\/api\/media\/images\/abcdef0123456789\.webp"/
  );
  assert.match(memberHtml, /loading="lazy"/);
});

test('vite.config.js defines production free-tier build optimization without sourcemaps', () => {
  const viteConfig = fs.readFileSync(
    path.resolve(process.cwd(), 'vite.config.js'),
    'utf-8'
  );
  assert.match(viteConfig, /sourcemap:\s*false/);
  assert.match(viteConfig, /outDir:\s*['"]dist['"]/);
  assert.match(viteConfig, /manualChunks/);
});

test('verifyDistDirectory passes valid RTL bundles and rejects raw A/V files or oversized dist output', () => {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'mahjar-dist-'));
  try {
    const validDist = path.join(tmpRoot, 'valid');
    fs.mkdirSync(path.join(validDist, 'assets'), { recursive: true });
    fs.writeFileSync(
      path.join(validDist, 'index.html'),
      '<!doctype html><html lang="ar" dir="rtl"><body><div id="root"></div></body></html>'
    );
    fs.writeFileSync(path.join(validDist, 'assets', 'index-abc123.js'), 'console.log(1);');
    fs.writeFileSync(path.join(validDist, 'assets', 'index-abc123.css'), 'body{}');

    const okResult = verifyDistDirectory(validDist);
    assert.equal(okResult.ok, true);
    assert.ok(okResult.totalBytes > 0);
    assert.equal(okResult.rawAvFiles.length, 0);

    // Raw video/audio file must fail verification
    const avDist = path.join(tmpRoot, 'with-av');
    fs.cpSync(validDist, avDist, { recursive: true });
    fs.writeFileSync(path.join(avDist, 'assets', 'intro.mp4'), 'video-bytes');
    assert.throws(() => verifyDistDirectory(avDist), /raw audio\/video/i);

    // Oversized bundle must fail free-tier budget check
    assert.throws(
      () => verifyDistDirectory(validDist, { maxTotalBytes: 10 }),
      /exceeds free-tier budget/i
    );
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});
