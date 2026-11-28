import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import esbuild from 'esbuild';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, '..');
const srcDir = path.join(rootDir, 'src');
const testsRootDir = path.join(srcDir, '__tests__');
const outDir = path.join(rootDir, 'node_modules', '.cache', 'test-bundles');

const ALLOWED_SUITES = new Set(['components', 'features', 'packaging']);

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

const args = process.argv.slice(2);
const suiteArgs = [];
const pathArgs = [];

for (const arg of args) {
  if (arg.startsWith('--suite=')) {
    const rawSuites = arg.slice('--suite='.length).split(',').map((s) => s.trim()).filter(Boolean);
    for (const suite of rawSuites) {
      if (!ALLOWED_SUITES.has(suite)) {
        console.error(
          `Unknown frontend test suite "${suite}". Allowed suites: ${Array.from(ALLOWED_SUITES).join(', ')}`
        );
        process.exit(1);
      }
      suiteArgs.push(suite);
    }
  } else {
    pathArgs.push(arg);
  }
}

let testFiles = [];
if (suiteArgs.length > 0) {
  for (const suite of suiteArgs) {
    testFiles.push(...findTestFiles(path.join(testsRootDir, suite)));
  }
} else if (pathArgs.length > 0) {
  for (const rawTarget of pathArgs) {
    const resolved = path.resolve(rootDir, rawTarget);
    if (!fs.existsSync(resolved)) {
      console.error(`Test target not found: ${rawTarget}`);
      process.exit(1);
    }
    const stat = fs.statSync(resolved);
    if (stat.isDirectory()) {
      testFiles.push(...findTestFiles(resolved));
    } else {
      testFiles.push(resolved);
    }
  }
} else {
  testFiles = findTestFiles(testsRootDir);
}

testFiles = Array.from(new Set(testFiles)).sort();

if (testFiles.length === 0) {
  console.error('No test files found for the specified selection.');
  process.exit(1);
}

const bundledFiles = [];
for (const file of testFiles) {
  const relName = path.relative(srcDir, file).replace(/[\\/]/g, '__').replace(/\.(js|jsx)$/, '.mjs');
  const outfile = path.join(outDir, relName);
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
