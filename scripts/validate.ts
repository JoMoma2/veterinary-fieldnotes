import {readLibrary,publicProjection} from '../src/lib/library';
const source=await readLibrary();const lib=publicProjection(source);
console.log(`Validated ${lib.articles.length} articles, ${lib.cases.length} cases, ${lib.shifts.length} shifts, ${lib.discussions.length} discussions, ${lib.questions.length} questions (${process.env.LIBRARY_DATASET??'production'}).`);
