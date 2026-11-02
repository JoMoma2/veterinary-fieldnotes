import { marked } from 'marked';
import sanitize from 'sanitize-html';
export const labels: Record<string, string> = {
  'direct-observation': 'Direct observation',
  'owner-report': 'Owner reported',
  'clinical-suspicion': 'Clinical suspicion',
  'confirmed-diagnosis': 'Confirmed diagnosis',
  'actual-treatment': 'Actual treatment',
  'proposed-treatment': 'Proposed treatment',
  outcome: 'Outcome',
  'ai-explanation': 'Educational explanation',
  'externally-verified': 'Externally verified',
  unknown: 'Unknown',
};
export function markdown(body: string) {
  return sanitize(marked.parse(body, { async: false }) as string, {
    allowedTags: sanitize.defaults.allowedTags,
    allowedAttributes: { a: ['href', 'title'] },
    allowedSchemes: ['https', 'http'],
    allowProtocolRelative: false,
  });
}
export function dateLabel(date: string) {
  return new Intl.DateTimeFormat('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(date + 'T12:00:00Z'));
}
export function offset(seconds: number) {
  const s = Math.floor(seconds);
  return `${Math.floor(s / 60)
    .toString()
    .padStart(2, '0')}:${(s % 60).toString().padStart(2, '0')}`;
}
export const discussionUrl = (id: string) => `/discussions/${id}/`;
