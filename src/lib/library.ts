import { readdir, readFile } from 'node:fs/promises';
import path from 'node:path';
import matter from 'gray-matter';
import {
  articleSchema,
  caseSchema,
  discussionSchema,
  questionSchema,
  shiftSchema,
  topicSchema,
  type Library,
  type PublicLibrary,
  type PublicRecord,
} from './schemas';

// This is the ONLY content root used by the website. Never glob private workspaces or repository roots.
export function contentRoot() {
  const dataset = process.env.LIBRARY_DATASET ?? 'production';
  if (!['production', 'demo', 'pipeline-demo'].includes(dataset))
    throw new Error('LIBRARY_DATASET must be production, demo, or pipeline-demo');
  return path.resolve(
    dataset === 'demo'
      ? 'fixtures/demo/public'
      : dataset === 'pipeline-demo'
        ? 'fixtures/generated/public'
        : 'content/public',
  );
}
export async function readLibrary(root = contentRoot()): Promise<Library> {
  const topics = topicSchema
    .array()
    .parse(JSON.parse(await readFile(path.join(root, 'topics.json'), 'utf8')));
  async function load(folder: string, markdown = false) {
    const names = (await readdir(path.join(root, folder)))
      .filter((f) => f.endsWith(markdown ? '.md' : '.json'))
      .sort();
    return Promise.all(
      names.map(async (name) => {
        const raw = await readFile(path.join(root, folder, name), 'utf8');
        if (!markdown) return JSON.parse(raw);
        const parsed = matter(raw);
        return { ...parsed.data, body: parsed.content };
      }),
    );
  }
  const [articles, cases, shifts, discussions, questions] = await Promise.all([
    load('articles', true),
    load('cases'),
    load('shifts'),
    load('discussions'),
    load('questions'),
  ]);
  const library = {
    topics,
    articles: articleSchema.array().parse(articles),
    cases: caseSchema.array().parse(cases),
    shifts: shiftSchema.array().parse(shifts),
    discussions: discussionSchema.array().parse(discussions),
    questions: questionSchema.array().parse(questions),
  };
  validateGraph(library);
  if (
    path.resolve(root) === path.resolve('content/public') &&
    [
      ...library.articles,
      ...library.cases,
      ...library.shifts,
      ...library.discussions,
      ...library.questions,
    ].some((e) => e.origin === 'synthetic')
  )
    throw new Error(
      'Synthetic records cannot enter the production content root; use a separate demonstration dataset',
    );
  return library;
}

export function validateGraph(lib: Library) {
  const groups = ['topics', 'articles', 'cases', 'shifts', 'discussions', 'questions'] as const;
  for (const group of groups) {
    const values = lib[group].map((v) => v.id);
    if (new Set(values).size !== values.length)
      throw new Error(`Duplicate permanent ID in ${group}`);
  }
  function refs(values: string[], group: (typeof groups)[number], owner: string) {
    const known = new Set(lib[group].map((v) => v.id));
    for (const value of values)
      if (!known.has(value)) throw new Error(`${owner}: missing ${group} reference ${value}`);
  }
  for (const group of groups.filter((g) => g !== 'topics'))
    for (const entry of lib[group]) refs(entry.topics, 'topics', entry.id);
  for (const article of lib.articles) {
    refs(article.sourceDiscussionIds, 'discussions', article.id);
    refs(article.relatedArticleIds, 'articles', article.id);
  }
  for (const item of [...lib.cases, ...lib.questions])
    refs(item.sourceDiscussionIds, 'discussions', item.id);
  for (const q of lib.questions) refs(q.articleIds, 'articles', q.id);
  for (const item of [...lib.cases, ...lib.discussions])
    for (const fact of item.facts) refs(fact.sourceDiscussionIds, 'discussions', item.id);
  for (const shift of lib.shifts) {
    if (new Set(shift.recordings.map((r) => r.id)).size !== shift.recordings.length)
      throw new Error(`${shift.id}: duplicate recording ID`);
    if (new Set(shift.recordings.map((r) => r.sequence)).size !== shift.recordings.length)
      throw new Error(`${shift.id}: duplicate recording sequence`);
    // Several discussions can begin at the same source block. Their permanent
    // IDs distinguish them; recording sequence and source bounds remain checked.
  }
  for (const d of lib.discussions) {
    refs([d.shiftId], 'shifts', d.id);
    refs(d.articleIds, 'articles', d.id);
    refs(d.caseIds, 'cases', d.id);
    const shift = lib.shifts.find((s) => s.id === d.shiftId)!;
    for (const segment of d.segments) {
      const r = shift.recordings.find((r) => r.id === segment.recordingId);
      if (!r || segment.endSeconds > r.durationSeconds)
        throw new Error(`${d.id}: recording segment outside recording bounds`);
      if (segment.clockConfidence === 'verified' && r.clockConfidence !== 'verified')
        throw new Error(`${d.id}: segment clock cannot be more certain than its recording`);
    }
  }
}

export function compareDiscussions(
  a: { order: number; id: string },
  b: { order: number; id: string },
) {
  return a.order - b.order || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
}

type Publishable = {
  origin: string;
  publication: {
    status: string;
    audience: string;
    reviewedBy?: string;
    reviewedAt?: string;
    authorizationRef?: string;
  };
};
export const canPublish = (v: Publishable) =>
  v.publication.status === 'approved' &&
  v.publication.audience === 'public' &&
  !!v.publication.reviewedBy &&
  !!v.publication.reviewedAt &&
  !!v.publication.authorizationRef;

// Only approved public records from the export root are eligible; private master data is never read.
// Strip review/authorization metadata from every browser-visible record, then remove non-public references.
export function publicProjection(input: Library): PublicLibrary {
  const lib = structuredClone(input);
  const strip = <T extends Publishable>(v: T): PublicRecord<T> => {
    const { publication: _, ...fields } = v;
    return fields as PublicRecord<T>;
  };
  const shifts = lib.shifts.filter(canPublish).map(strip);
  const discussions = lib.discussions
    .filter((d) => canPublish(d) && shifts.some((s) => s.id === d.shiftId))
    .map(strip);
  const articles = lib.articles.filter(canPublish).map(strip);
  const cases = lib.cases
    .filter(
      (c) =>
        canPublish(c) && c.sourceDiscussionIds.some((id) => discussions.some((d) => d.id === id)),
    )
    .map(strip);
  const questions = lib.questions.filter(canPublish).map(strip);
  for (const shift of shifts) {
    const visibleRecordings = new Set(
      discussions
        .filter((d) => d.shiftId === shift.id)
        .flatMap((d) => d.segments.map((s) => s.recordingId)),
    );
    shift.recordings = shift.recordings.filter((r) => visibleRecordings.has(r.id));
  }
  const visibleD = new Set(discussions.map((d) => d.id)),
    visibleA = new Set(articles.map((a) => a.id)),
    visibleC = new Set(cases.map((c) => c.id));
  const keepD = (ids: string[]) => ids.filter((id) => visibleD.has(id));
  // Bidirectional relationships are derived from either end, without requiring an extraction model to write both.
  for (const a of articles)
    a.sourceDiscussionIds = [
      ...new Set([
        ...keepD(a.sourceDiscussionIds),
        ...discussions.filter((d) => d.articleIds.includes(a.id)).map((d) => d.id),
      ]),
    ];
  for (const c of cases)
    c.sourceDiscussionIds = [
      ...new Set([
        ...keepD(c.sourceDiscussionIds),
        ...discussions.filter((d) => d.caseIds.includes(c.id)).map((d) => d.id),
      ]),
    ];
  for (const d of discussions) {
    d.articleIds = [
      ...new Set([
        ...d.articleIds.filter((id) => visibleA.has(id)),
        ...articles.filter((a) => a.sourceDiscussionIds.includes(d.id)).map((a) => a.id),
      ]),
    ];
    d.caseIds = [
      ...new Set([
        ...d.caseIds.filter((id) => visibleC.has(id)),
        ...cases.filter((c) => c.sourceDiscussionIds.includes(d.id)).map((c) => c.id),
      ]),
    ];
    d.facts = d.facts.map((f) => ({ ...f, sourceDiscussionIds: keepD(f.sourceDiscussionIds) }));
  }
  for (const c of cases)
    c.facts = c.facts.map((f) => ({ ...f, sourceDiscussionIds: keepD(f.sourceDiscussionIds) }));
  for (const a of articles)
    a.relatedArticleIds = a.relatedArticleIds.filter((id) => visibleA.has(id));
  for (const q of questions) {
    q.articleIds = q.articleIds.filter((id) => visibleA.has(id));
    q.sourceDiscussionIds = keepD(q.sourceDiscussionIds);
  }
  // Publication metadata is intentionally absent at runtime. Deep clone prevents mutations of the master input.
  return {
    topics: lib.topics,
    articles,
    cases,
    shifts,
    discussions,
    questions: questions.filter((q) => q.sourceDiscussionIds.length > 0),
  };
}
export async function getLibrary() {
  return publicProjection(structuredClone(await readLibrary()));
}
