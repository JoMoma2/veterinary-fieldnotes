import type { PublicQuestion as Question } from './schemas';
export const formats = {'multiple-choice':'Multiple choice','multiple-select':'Multiple select',flashcard:'Flashcards','open-ended':'Open ended',scenario:'Clinical scenarios'} as const;
export function shuffle<T>(items:readonly T[], random:()=>number=Math.random):T[] {
  const out=[...items]; for(let i=out.length-1;i>0;i--) {const j=Math.floor(random()*(i+1));[out[i],out[j]]=[out[j],out[i]];}return out;
}
export function optionsFor(q:Question, random:()=>number=Math.random) {
  if(q.format==='multiple-choice') return shuffle([q.correct,...shuffle(q.distractors,random).slice(0,3)],random);
  if(q.format==='multiple-select') return shuffle(q.choices,random);
  return [];
}
export function isCorrect(q:Question, selected:string[]) {
  const expected=q.format==='multiple-choice'?[q.correct.id]:q.format==='multiple-select'?q.correctIds:[];
  return expected.length>0 && new Set(selected).size===expected.length && expected.every(id=>selected.includes(id));
}
export function selectQuestions(questions:Question[],topics:string[],formats:string[]) {
  return questions.filter(q=>q.topics.some(t=>topics.includes(t))&&formats.includes(q.format));
}
