import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import esbuild from 'esbuild';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');
const srcDir = path.join(rootDir, 'src');
const outDir = path.join(rootDir, 'node_modules', '.cache', 'test-bundles');

fs.mkdirSync(outDir, { recursive: true });

function findTestFiles(dir) {
  const results = [];
  if (!fs.existsSync(dir)) return results;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      results.push(...findTestFiles(fullPath));
    } else if (/\.test\.(js|jsx)$/.test(entry.name)) {
      results.push(fullPath);
    }
  }
  return results;
}

const testFiles = findTestFiles(srcDir);
if (testFiles.length === 0) {
  console.error('No test files found in src/');
  process.exit(1);
}

const bundledFiles = [];
for (const file of testFiles) {
  const outName = path.basename(file).replace(/\.(js|jsx)$/, '.mjs');
  const outfile = path.join(outDir, outName);
  await esbuild.build({
    entryPoints: [file],
    outfile,
    bundle: true,
    platform: 'node',
    format: 'esm',
    jsx: 'automatic',
    loader: { '.css': 'empty' },
    external: ['react', 'react-dom', 'react-dom/server'],
    logLevel: 'error',
  });
  bundledFiles.push(outfile);
}

const result = spawnSync(process.execPath, ['--test', ...bundledFiles], {
  stdio: 'inherit',
});

process.exit(result.status ?? 1);
