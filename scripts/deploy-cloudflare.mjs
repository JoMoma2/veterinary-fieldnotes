import { readFile } from 'node:fs/promises';
import { spawnSync } from 'node:child_process';
const dataset = process.env.LIBRARY_DATASET ?? 'production';
const info = JSON.parse(await readFile('dist/build-info.json', 'utf8'));
if (dataset !== 'production' || info.dataset !== 'production')
  throw new Error('Only a production build may be deployed');
// Wrangler uses protected local OAuth for owner commands or environment credentials in CI.
const result = spawnSync(
  'npm',
  [
    'exec',
    '--',
    'wrangler',
    'pages',
    'deploy',
    'dist',
    '--project-name',
    process.env.CLOUDFLARE_PROJECT_NAME ?? 'veterinary-fieldnotes',
    '--branch',
    'main',
  ],
  { stdio: 'inherit', env: process.env },
);
process.exit(result.status ?? 1);
