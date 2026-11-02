import { z } from 'zod';

export const id = z.string().regex(/^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$/, 'Use a permanent lowercase, hyphenated ID');
const text = z.string().trim().min(1);
const ids = z.array(id).refine(v => new Set(v).size === v.length, 'Duplicate reference');
const date = z.iso.date();
const publication = z.strictObject({
  status: z.enum(['draft', 'approved', 'withheld']), audience: z.enum(['private', 'public']),
  reviewedBy: text.optional(), reviewedAt: z.iso.datetime().optional(), authorizationRef: text.optional(),
}).superRefine((v, ctx) => {
  if (v.status === 'approved' && v.audience === 'public' && (!v.reviewedBy || !v.reviewedAt || !v.authorizationRef))
    ctx.addIssue({ code: 'custom', message: 'Public approval requires reviewer, review time, and authorization reference' });
});
const common = { schemaVersion: z.literal(1), id, origin: z.enum(['synthetic', 'authorized-record']), publication };
export const topicSchema = z.strictObject({ id, name: text, description: text, color: z.enum(['green', 'amber', 'blue', 'rose']) });
export const articleSchema = z.strictObject({ ...common, title: text, summary: text, topics: ids.min(1),
  updated: date, sourceDiscussionIds: ids, relatedArticleIds: ids, body: text,
  educationalStatus: z.enum(['synthetic-demonstration', 'unreviewed-extraction', 'reviewed-education']),
});
// File metadata and audio offsets remain distinct. Clock timestamps must never be inferred from accumulated audio duration.
export const recordingSchema = z.strictObject({ id, sequence: z.number().int().nonnegative(),
  durationSeconds: z.number().nonnegative(), fileModifiedAt: z.iso.datetime({offset:true}).nullable().optional(), sourceSha256: z.string().regex(/^[a-f0-9]{64}$/).optional(), capturedAt: z.iso.datetime({ offset: true }).nullable(),
  clockConfidence: z.enum(['verified', 'device-unverified', 'unknown']),
}).superRefine((v, c) => { if (v.clockConfidence === 'verified' && v.capturedAt === null) c.addIssue({code:'custom', message:'Verified recording requires capturedAt'}); });
export const shiftSchema = z.strictObject({ ...common, title: text, date, summary: text, topics: ids,
  timezone: text, recordings: z.array(recordingSchema),
  processing: z.enum(['complete', 'partial']),
});
export const sourceSegmentSchema = z.strictObject({ recordingId: id, startSeconds: z.number().nonnegative(), endSeconds: z.number().nonnegative(),
  clockTime: z.iso.datetime({ offset: true }).nullable(), clockConfidence: z.enum(['verified', 'device-unverified', 'unknown']),
}).superRefine((v,c) => {
  if(v.endSeconds <= v.startSeconds) c.addIssue({code:'custom', message:'Segment end must be after start'});
  if(v.clockConfidence === 'verified' && v.clockTime === null) c.addIssue({code:'custom', message:'Verified clock time required'});
});
export const evidenceKinds = ['direct-observation','owner-report','clinical-suspicion','confirmed-diagnosis','actual-treatment','proposed-treatment','outcome','ai-explanation','externally-verified','unknown'] as const;
export const factSchema = z.strictObject({ kind: z.enum(evidenceKinds), text,
  sourceDiscussionIds: ids, externalUrl: z.url().optional(),
}).superRefine((v,c) => { if(v.kind === 'externally-verified' && !v.externalUrl) c.addIssue({code:'custom',message:'Externally verified claims require a source URL'}); });
export const discussionSchema = z.strictObject({ ...common, shiftId: id, order: z.number().int().nonnegative(),
  title: text, topics: ids.min(1), segments: z.array(sourceSegmentSchema).min(1),
  account: text, facts: z.array(factSchema), questions: z.array(text), conclusions: text,
  articleIds: ids, caseIds: ids,
});
export const caseSchema = z.strictObject({ ...common, title: text, summary: text, topics: ids.min(1),
  species: text, patientLabel: text, diagnosis: text.nullable(), outcome: text.nullable(),
  sourceDiscussionIds: ids.min(1), facts: z.array(factSchema).min(1),
  linkBasis: text, uncertainties: z.array(text).min(1),
});
const questionBase = { ...common, topics: ids.min(1), prompt: text, explanation: text,
  articleIds: ids, sourceDiscussionIds: ids.min(1) };
const choice = z.strictObject({ id, text });
export const questionSchema = z.discriminatedUnion('format', [
  z.strictObject({...questionBase, format: z.literal('multiple-choice'), correct: choice, distractors: z.array(choice).min(3).max(9)}),
  z.strictObject({...questionBase, format: z.literal('multiple-select'), choices: z.array(choice).min(3), correctIds: ids.min(1)}),
  z.strictObject({...questionBase, format: z.enum(['flashcard','open-ended','scenario']), answer: text}),
]).superRefine((v,c) => {
  if(v.format === 'multiple-choice') {
    const all=[v.correct,...v.distractors];
    if(new Set(all.map(a=>a.id)).size!==all.length || new Set(all.map(a=>a.text.toLowerCase())).size!==all.length)
      c.addIssue({code:'custom',message:'Answer IDs and text must be unique'});
  }
  if(v.format === 'multiple-select') {
    const all = v.choices.map(a=>a.id);
    if(new Set(all).size !== all.length || new Set(v.choices.map(a=>a.text.toLowerCase())).size !== all.length || v.correctIds.some(a=>!all.includes(a)) || v.correctIds.length === all.length)
      c.addIssue({code:'custom',message:'Multiple-select needs unique answers, known correct IDs, and an incorrect option'});
  }
});
export type Topic = z.infer<typeof topicSchema>;
export type Article = z.infer<typeof articleSchema>;
export type Shift = z.infer<typeof shiftSchema>;
export type Discussion = z.infer<typeof discussionSchema>;
export type ClinicalCase = z.infer<typeof caseSchema>;
export type Question = z.infer<typeof questionSchema>;
export type Fact = z.infer<typeof factSchema>;
export interface Library { topics: Topic[]; articles: Article[]; cases: ClinicalCase[]; shifts: Shift[]; discussions: Discussion[]; questions: Question[] }

export type PublicRecord<T> = T extends {publication: unknown} ? Omit<T,'publication'> : T;
export type PublicQuestion = PublicRecord<Question>;
export type PublicLibrary = { [K in keyof Library]: PublicRecord<Library[K][number]>[] };
