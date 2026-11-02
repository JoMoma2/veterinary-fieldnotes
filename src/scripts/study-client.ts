import type {PublicQuestion as Question} from '../lib/schemas';
import {formats,shuffle,optionsFor,isCorrect,selectQuestions} from '../lib/study';
const form=document.querySelector<HTMLFormElement>('#study-settings');
const area=document.querySelector<HTMLElement>('#study-session');
const data=document.getElementById('study-data');
function el<K extends keyof HTMLElementTagNameMap>(tag:K,text?:string,className?:string) {const e=document.createElement(tag);if(text)e.textContent=text;if(className)e.className=className;return e;}
if(form&&area&&data){
 const questions:Question[]=JSON.parse(data.textContent!);let queue:Question[]=[];let index=0;
 const topicInputs=Array.from(form.querySelectorAll<HTMLInputElement>('input[name=topic]'));
 const initial=new URLSearchParams(location.search).get('topic');if(initial&&topicInputs.some(i=>i.value===initial))topicInputs.forEach(i=>i.checked=i.value===initial);
 document.getElementById('select-all')!.addEventListener('click',()=>topicInputs.forEach(i=>i.checked=true));
 document.getElementById('deselect-all')!.addEventListener('click',()=>topicInputs.forEach(i=>i.checked=false));
 form.addEventListener('submit',e=>{e.preventDefault();const values=new FormData(form);queue=shuffle(selectQuestions(questions,values.getAll('topic') as string[],values.getAll('format') as string[]));index=0;
 const error=document.getElementById('study-error')!;
 if(!queue.length){error.textContent='No questions match. Select at least one subject and format with available questions.';error.classList.remove('sr-only');area.replaceChildren(el('h2','No matching questions'),el('p','Change your subjects or formats and try again.'));return;}
 error.classList.add('sr-only');render();});
 function render(){const q=queue[index];area!.replaceChildren();
 const toolbar=el('div',undefined,'study-toolbar');toolbar.append(el('span',`${index+1} of ${queue.length}`,'muted'),el('span',formats[q.format],'tag green'));area!.append(toolbar);
 const heading=el('h2',q.prompt,'study-question');heading.tabIndex=-1;area!.append(heading);heading.focus();
 const choiceForm=el('form');const options=optionsFor(q);const optionArea=el('fieldset',undefined,'answer-options');optionArea.style.border='0';optionArea.style.padding='0';optionArea.append(el('legend',q.format==='multiple-select'?'Select every supported answer':'Choose one answer','sr-only'));
 for(const option of options){const label=el('label',undefined,'answer-option');const input=el('input');input.type=q.format==='multiple-select'?'checkbox':'radio';input.name='answer';input.value=option.id;label.append(input,el('span',option.text));optionArea.append(label);}
 if(options.length)choiceForm.append(optionArea);
 const actions=el('div',undefined,'study-actions');const submit=el('button',options.length?'Check answer':'Reveal model answer','button primary');submit.type='submit';actions.append(submit);choiceForm.append(actions);area!.append(choiceForm);
 choiceForm.addEventListener('submit',e=>{e.preventDefault();const selected=Array.from(choiceForm.querySelectorAll<HTMLInputElement>('input:checked')).map(i=>i.value);
 if(options.length&&!selected.length){let err=choiceForm.querySelector('[role=alert]');if(!err){err=el('p','Choose an answer before checking.','muted');err.setAttribute('role','alert');actions.before(err);}return;}
 choiceForm.querySelector('[role=alert]')?.remove();submit.disabled=true;
 const expected=q.format==='multiple-choice'?[q.correct.id]:q.format==='multiple-select'?q.correctIds:[];
 const correct=options.length?isCorrect(q,selected):true;
 choiceForm.querySelectorAll<HTMLInputElement>('input').forEach(input=>{input.disabled=true;input.parentElement!.classList.toggle('correct',expected.includes(input.value));input.parentElement!.classList.toggle('incorrect',selected.includes(input.value)&&!expected.includes(input.value));});
 const feedback=el('div',undefined,'feedback');feedback.setAttribute('role','status');feedback.append(el('h3',options.length?(correct?'That’s correct.':'Let’s look at the evidence.'):'Compare with the model answer'));
 if('answer' in q)feedback.append(el('p',q.answer,'model-answer'));else feedback.append(el('p',`Correct answer${expected.length>1?'s':''}: ${options.filter(o=>expected.includes(o.id)).map(o=>o.text).join('; ')}`));
 feedback.append(el('p',q.explanation));for(const id of q.articleIds){const a=el('a','Read the connected knowledge article →');a.href=`/knowledge/${id}/`;feedback.append(a);}for(const id of q.sourceDiscussionIds){const a=el('a','Return to the source discussion ↗');a.href=`/discussions/${id}/`;feedback.append(a);}
 const next=el('button',index+1<queue.length?'Next question →':'Finish session','button primary');next.type='button';next.addEventListener('click',()=>{index++;if(index<queue.length)render();else{area!.replaceChildren(el('h2','A little more knowledge, connected.'),el('p','Session complete. Choose your subjects to practice again. No progress has been stored.'));}});feedback.append(next);area!.append(feedback);
 },{once:false});
 }
}
