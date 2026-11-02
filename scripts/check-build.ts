import { readdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { load } from 'cheerio';
import { getLibrary } from '../src/lib/library';
async function files(dir: string): Promise<string[]> {
  const entries = await readdir(dir, { withFileTypes: true });
  return (
    await Promise.all(
      entries.map((e) =>
        e.isDirectory() ? files(path.join(dir, e.name)) : Promise.resolve([path.join(dir, e.name)]),
      ),
    )
  ).flat();
}
const all = await files('dist');
const htmls = all.filter((f) => f.endsWith('.html'));
const docs = new Map<string, ReturnType<typeof load>>();
for (const file of htmls)
  docs.set(
    '/' + path.relative('dist', file).replace(/index\.html$/, ''),
    load(await readFile(file, 'utf8')),
  );
let links = 0;
for (const [url, $] of docs) {
  for (const a of $('a[href]').toArray()) {
    const href = $(a).attr('href')!;
    if (!href.startsWith('/') && !href.startsWith('#')) continue;
    const u = new URL(href, 'http://local' + url);
    const key = u.pathname;
    const dest = docs.get(key);
    if (!dest) throw new Error(`${url}: missing route ${href}`);
    if (u.hash && !dest(`[id="${decodeURIComponent(u.hash.slice(1))}"]`).length)
      throw new Error(`${url}: missing anchor ${href}`);
    links++;
  }
}
for (const file of all.filter((f) => /\.(json|html|js|map|md|wav)$/i.test(f))) {
  const text = await readFile(file, 'utf8');
  if (text.includes('PRIVATE_TEST_SENTINEL')) throw new Error(`Private sentinel leaked: ${file}`);
  if (file.endsWith('.map') || file.endsWith('.wav')) throw new Error(`Forbidden output: ${file}`);
}
console.log(
  `Verified ${htmls.length} HTML pages and ${links} internal links/anchors; no private sentinel, source maps, or audio.`,
);

const publicLibrary = await getLibrary();
await writeFile(
  'dist/build-info.json',
  JSON.stringify({
    dataset: process.env.LIBRARY_DATASET ?? 'production',
    builtAt: new Date().toISOString(),
    commit: process.env.CF_PAGES_COMMIT_SHA ?? process.env.GITHUB_SHA ?? null,
    recordCounts: Object.fromEntries(
      ['articles', 'cases', 'shifts', 'discussions', 'questions'].map((k) => [
        k,
        publicLibrary[k as keyof typeof publicLibrary].length,
      ]),
    ),
  }),
);
