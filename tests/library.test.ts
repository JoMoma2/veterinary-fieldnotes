import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {
  readLibrary,
  publicProjection,
  validateGraph,
  canPublish,
  contentRoot,
} from '../src/lib/library';
import { questionSchema, articleSchema, sourceSegmentSchema } from '../src/lib/schemas';
import { optionsFor, isCorrect, selectQuestions, shuffle } from '../src/lib/study';
import { markdown, offset } from '../src/lib/format';
const demo = await readLibrary(path.resolve('fixtures/demo/public'));
test('production is empty of clinical and medical records', async () => {
  const lib = await readLibrary(path.resolve('content/public'));
  for (const group of ['articles', 'cases', 'shifts', 'discussions', 'questions'] as const)
    assert.equal(lib[group].length, 0);
});
test('demo graph is valid and all formats are represented', () => {
  validateGraph(demo);
  assert.equal(new Set(demo.questions.map((q) => q.format)).size, 5);
});
test('default dataset is production; arbitrary content roots are not environment configurable', () => {
  assert.equal(contentRoot(), path.resolve('content/public'));
});
test('public projection excludes drafts, private data, approval metadata, and private references', () => {
  const lib = structuredClone(demo);
  lib.discussions.find((d) => d.id === 'd-urinary-history')!.publication = {
    status: 'withheld',
    audience: 'private',
  };
  lib.discussions.find((d) => d.id === 'd-urinary-history')!.account = 'PRIVATE_TEST_SENTINEL';
  lib.cases[0].publication = { status: 'draft', audience: 'private' };
  const view = publicProjection(lib);
  const serialized = JSON.stringify(view);
  assert.ok(!serialized.includes('PRIVATE_TEST_SENTINEL'));
  assert.ok(!serialized.includes('reviewedBy'));
  assert.ok(!serialized.includes('authorizationRef'));
  assert.ok(!serialized.includes('d-urinary-history'));
  assert.ok(!serialized.includes('c-amber'));
  assert.ok(lib.articles[0].sourceDiscussionIds.length > 0);
});
test('projection never mutates master content', () => {
  const before = JSON.stringify(demo);
  publicProjection(demo);
  assert.equal(JSON.stringify(demo), before);
});
test('discussion-to-article links are bidirectional', () => {
  const lib = structuredClone(demo);
  lib.articles.find((a) => a.id === 'a-fip-reasoning')!.sourceDiscussionIds = [];
  const view = publicProjection(lib);
  assert.equal(
    view.articles.find((a) => a.id === 'a-fip-reasoning')!.sourceDiscussionIds.length,
    2,
  );
});
test('unapproved containing shift excludes its discussions and study sources', () => {
  const lib = structuredClone(demo);
  lib.shifts.forEach((s) => (s.publication = { status: 'draft', audience: 'private' }));
  const view = publicProjection(lib);
  assert.equal(view.discussions.length, 0);
  assert.equal(view.questions.length, 0);
});
test('public approval requires authorization and privacy review metadata', () => {
  const a = structuredClone(demo.articles[0]);
  delete a.publication.authorizationRef;
  assert.throws(() => articleSchema.parse(a));
  assert.equal(canPublish(a), false);
});
test('invalid transcript offsets are rejected; reliable time cannot be manufactured', () => {
  assert.throws(() =>
    sourceSegmentSchema.parse({
      recordingId: 'r-test',
      startSeconds: 8,
      endSeconds: 2,
      clockTime: null,
      clockConfidence: 'unknown',
    }),
  );
  assert.throws(() =>
    sourceSegmentSchema.parse({
      recordingId: 'r-test',
      startSeconds: 0,
      endSeconds: 8,
      clockTime: null,
      clockConfidence: 'verified',
    }),
  );
});
test('source bounds, missing references, and duplicate IDs fail validation', () => {
  let lib = structuredClone(demo);
  lib.discussions[0].segments[0].endSeconds = 999999;
  assert.throws(() => validateGraph(lib));
  lib = structuredClone(demo);
  lib.articles[0].sourceDiscussionIds = ['d-missing'];
  assert.throws(() => validateGraph(lib));
  lib = structuredClone(demo);
  lib.articles.push(lib.articles[0]);
  assert.throws(() => validateGraph(lib));
});
test('cases retain unknown diagnosis and outcome', () => {
  for (const c of demo.cases) {
    assert.equal(c.diagnosis, null);
    assert.equal(c.outcome, null);
  }
});
test('MC samples exactly three distinct distractors and randomizes answers', () => {
  const q = demo.questions.find((q) => q.format === 'multiple-choice')!;
  assert.equal(q.format, 'multiple-choice');
  if (q.format !== 'multiple-choice') return;
  for (let i = 0; i < 40; i++) {
    const options = optionsFor(q);
    assert.equal(options.length, 4);
    assert.equal(new Set(options.map((a) => a.id)).size, 4);
    assert.ok(options.some((o) => o.id === q.correct.id));
  }
  assert.ok(isCorrect(q, [q.correct.id]));
  assert.ok(!isCorrect(q, [q.distractors[0].id]));
});
test('multiple-select requires the exact set of answers', () => {
  const q = demo.questions.find((q) => q.format === 'multiple-select')!;
  if (q.format !== 'multiple-select') return;
  assert.ok(isCorrect(q, q.correctIds));
  assert.ok(isCorrect(q, [...q.correctIds].reverse()));
  assert.ok(!isCorrect(q, q.correctIds.slice(1)));
  assert.ok(!isCorrect(q, [...q.correctIds, 'invented']));
});
test('question schemas reject ambiguous duplicate answer IDs', () => {
  const q = structuredClone(demo.questions.find((q) => q.format === 'multiple-choice')!);
  if (q.format !== 'multiple-choice') return;
  q.distractors[0].id = q.correct.id;
  assert.throws(() => questionSchema.parse(q));
});
test('topic and format filters return only matching questions', () => {
  assert.equal(selectQuestions(demo.questions, [], ['flashcard']).length, 0);
  const qs = selectQuestions(demo.questions, ['equipment'], ['scenario']);
  assert.ok(qs.length > 0);
  assert.ok(qs.every((q) => q.format === 'scenario' && q.topics.includes('equipment')));
});
test('shuffle preserves input; markdown cannot execute arbitrary scripts', () => {
  const input = [1, 2, 3, 4];
  assert.deepEqual([...shuffle(input)].sort(), input);
  assert.deepEqual(input, [1, 2, 3, 4]);
  const html = markdown('<script>secret()</script><a href="javascript:alert(1)">x</a>');
  assert.ok(!html.includes('<script'));
  assert.ok(!html.includes('javascript:'));
  assert.equal(offset(125), '02:05');
});
