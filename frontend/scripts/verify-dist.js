import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const RAW_AV_EXTENSIONS = new Set([
  '.mp4',
  '.mov',
  '.avi',
  '.mkv',
  '.webm',
  '.m4v',
  '.3gp',
  '.mp3',
  '.wav',
  '.ogg',
  '.m4a',
  '.aac',
  '.flac',
  '.wma',
]);

export const DEFAULT_MAX_DIST_BYTES = 5 * 1024 * 1024;

function walkFiles(dir) {
  const files = [];
  if (!fs.existsSync(dir)) return files;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkFiles(fullPath));
    } else if (entry.isFile()) {
      files.push(fullPath);
    }
  }
  return files;
}

export function verifyDistDirectory(
  distDir,
  { maxTotalBytes = DEFAULT_MAX_DIST_BYTES } = {}
) {
  const resolvedDist = path.resolve(distDir);
  if (!fs.existsSync(resolvedDist) || !fs.statSync(resolvedDist).isDirectory()) {
    throw new Error(`Build directory not found: ${resolvedDist}`);
  }

  const indexPath = path.join(resolvedDist, 'index.html');
  if (!fs.existsSync(indexPath)) {
    throw new Error(`Missing index.html in build output: ${resolvedDist}`);
  }

  const indexHtml = fs.readFileSync(indexPath, 'utf-8');
  if (!/dir=["']rtl["']/i.test(indexHtml) || !/lang=["']ar["']/i.test(indexHtml)) {
    throw new Error('Built index.html must preserve lang="ar" and dir="rtl".');
  }

  const allFiles = walkFiles(resolvedDist);
  let totalBytes = 0;
  const rawAvFiles = [];
  const assetFiles = [];

  for (const filePath of allFiles) {
    const stat = fs.statSync(filePath);
    totalBytes += stat.size;
    const relPath = path.relative(resolvedDist, filePath);
    const ext = path.extname(filePath).toLowerCase();
    if (RAW_AV_EXTENSIONS.has(ext)) {
      rawAvFiles.push(relPath);
    }
    if (relPath.startsWith(`assets${path.sep}`) || relPath.startsWith('assets/')) {
      assetFiles.push(relPath);
    }
  }

  if (rawAvFiles.length > 0) {
    throw new Error(
      `Disallowed raw audio/video files found in dist/: ${rawAvFiles.join(', ')}`
    );
  }

  const hasJsAsset = assetFiles.some((f) => f.endsWith('.js'));
  if (!hasJsAsset) {
    throw new Error('Expected at least one compiled JS bundle under dist/assets/.');
  }

  if (totalBytes > maxTotalBytes) {
    throw new Error(
      `Dist bundle size (${totalBytes} bytes) exceeds free-tier budget (${maxTotalBytes} bytes).`
    );
  }

  return {
    ok: true,
    fileCount: allFiles.length,
    totalBytes,
    rawAvFiles,
    assetFiles,
  };
}

const isMain =
  typeof process !== 'undefined' &&
  Array.isArray(process.argv) &&
  process.argv[1] &&
  path.basename(process.argv[1]) === 'verify-dist.js' &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);

if (isMain) {
  const __dirname = path.dirname(fileURLToPath(import.meta.url));
  const defaultDist = path.resolve(__dirname, '..', 'dist');
  const summary = verifyDistDirectory(defaultDist);
  console.log(
    `Verified frontend dist (${summary.fileCount} files, ${(summary.totalBytes / 1024).toFixed(1)} KiB, 0 raw A/V assets).`
  );
}
