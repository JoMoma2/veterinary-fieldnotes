"""Readable, owner-only HTML/Markdown for the whole-shift context experiment."""
import base64
import hashlib
import html
import json
import re

from .private import private_path
from .util import atomic_write, load_json


SCRIPT = """document.addEventListener('click',event=>{
const b=event.target.closest('button[data-audio]');if(!b)return;
const a=document.getElementById('player'),t=Number(b.dataset.start),src=b.dataset.audio;
if(!Number.isFinite(t)||t<0||!src.startsWith('../inputs/'))return;
const seek=()=>{a.currentTime=t;};
if(a.getAttribute('src')!==src){a.src=src;a.addEventListener('loadedmetadata',seek,{once:true});}
else if(a.readyState)seek();else a.addEventListener('loadedmetadata',seek,{once:true});
a.play().catch(()=>{document.getElementById('player-status').textContent='Use the audio player Play button if automatic playback is blocked.';});
document.getElementById('player-label').textContent=b.dataset.label;
});"""


def render_report(root):
    from .shift_context import name_hints
    root = private_path(root)
    experiment = load_json(root / 'experiment.json')
    sources = load_json(root / 'sources.json'); recordings = load_json(root / 'recordings.json')
    index = load_json(root / 'index-map.json') if (root / 'index-map.json').exists() else {'episodes': []}
    e = lambda value: html.escape(str(value), quote=True)
    episodes = index['episodes']; completed = []
    aliases = load_json(root / 'owner-aliases.json') if (root / 'owner-aliases.json').exists() else {}
    metrics = []
    for call in sorted((root / 'calls').glob('*.json')) if (root / 'calls').exists() else []:
        if call.stem == 'index' or re.fullmatch(r'episode-\d{3}', call.stem):
            saved = load_json(call); metrics.append(saved['metrics'])
    for number, episode in enumerate(episodes, 1):
        file = root / 'calls' / f'episode-{number:03d}.json'
        if file.exists():
            completed.append((number, episode, load_json(file)['data']))
    eligible = sum(s['eligible'] for s in sources.values())
    used = set()
    body = '<h1>Last night — whole-context extraction experiment</h1><p><strong>Private AI draft. Not published, medically verified, or approved.</strong> Patient associations are model proposals. Ambiguous switches and transcription errors remain possible.</p>'
    body += '<section><h2>Progress and configuration</h2><p>Status: <strong>' + e(experiment['status']) + '</strong>; detailed episodes saved: ' + str(len(completed)) + '/' + str(len(episodes)) + '.</p>'
    body += '<p>' + str(len(recordings)) + ' recordings selected; ' + str(sum(bool(r['blocks']) for r in recordings)) + ' parsed transcripts reused. ' + str(sum(r['status'] == 'context-only-ASR-warning' for r in recordings)) + ' parsed transcripts are context-only due to ASR warnings; ' + str(sum(not r['blocks'] for r in recordings)) + ' have no valid parsed transcript. No Whisper inference is run.</p>'
    body += '<p>' + e(experiment['provider']['model']) + '; context ' + str(experiment['provider']['context_window']) + ' tokens; requested GPU layers ' + str(experiment['gpuLayers']) + '; whole available parsed-night context supplied to each model request. Original recording clocks remain unverified.</p>'
    body += '<p>Reasoning mode: ' + ('enabled' if experiment.get('thinking') else 'disabled') + '; maximum generated tokens: ' + str(experiment['provider']['max_output_tokens']) + '. This is a combined context/prompt/synthesis experiment, not a controlled measurement of context alone.</p>'
    if experiment.get('focusedEvidence'):
        body += '<p><strong>Focused-evidence variant:</strong> the complete night is retained, with extra copies of selected original passages near the writing task. Same model, context allocation and output allowance; source copies are budgeted without removing original context.</p>'
    body += '<p><strong>Study question drafts require independent medical fact checking.</strong> Transcript citations establish what was said, not medical correctness. Use the Morning Review fact-checking report before studying these drafts.</p>'
    if experiment.get('medicalOnlyQuestions'):
        body += '<p><strong>Study policy:</strong> self-contained, transferable medical knowledge only; no case recall, case vignettes, names/dates, quotation completion or nonmedical workflow questions. Zero questions is acceptable. Passing citation checks is not medical verification.</p>'
    if experiment.get('repetitionExclusionThreshold'):
        body += '<p><strong>Repetition filter:</strong> consecutive phrases repeated ' + e(experiment['repetitionExclusionThreshold']) + ' or more times are excluded from AI input/evidence. Full original transcripts remain in the speaker/source review below. This heuristic can also exclude real repetition; it is not a hallucination detector.</p>'
    if experiment.get('speakerLabels'):
        body += '<p><a href="speakers.html">Speaker-labelled full transcript and audio review</a>. Voice labels are anonymous, shift-scoped and unverified. Mixed/unknown segments are not forced onto one person.</p>'
    if metrics:
        body += '<p>Saved inference wall time: ' + e(round(sum(m.get('seconds', 0) for m in metrics), 1)) + ' s; maximum reported input tokens: ' + str(max(m.get('prompt_eval_count', 0) or 0 for m in metrics)) + '; peak sampled GPU allocation: ' + str(max(m.get('peakGpuMiB', 0) for m in metrics)) + ' MiB.</p>'
    if experiment.get('lastErrorClass'):
        body += '<p class="warning">Last attempt: ' + e(experiment['lastErrorClass']) + '. Successful saved outputs remain available; incomplete work is not presented as complete.</p>'
    body += '<p>Refresh to see newly saved episodes. <a href="#sources">Full source transcripts / raw review</a> · <a href="#baseline">Previous output for comparison</a></p></section>'
    if index.get('limitations'):
        body += '<section><h2>Whole-night limitations reported by the model</h2><ul>' + ''.join('<li>' + e(x) + '</li>' for x in index['limitations']) + '</ul></section>'
    body += '<section class="player"><strong id="player-label">Listen to a source using its timestamp button below</strong><audio id="player" controls preload="none"></audio><p id="player-status" role="status"></p></section>'
    markdown = ['# Last night — whole-context extraction experiment', '', '**PRIVATE, UNREVIEWED AI DRAFT — no public publication.**', '', 'Status: ' + experiment['status'], '']

    def evidence(refs):
        out = '<details><summary>Source evidence and audio</summary>'
        for ref in refs:
            block = sources.get(ref['source'])
            if not block:
                continue
            used.add(ref['source'])
            label = f'Recording {block["recordingNumber"]}, {block["start"]:.2f}–{block["end"]:.2f}s'
            out += '<blockquote>' + e(ref['quote']) + '</blockquote><p><a href="#' + e(ref['source']) + '">' + e(label) + '</a> '
            if (root / 'inputs' / (block['recordingId'] + '.wav')).exists():
                out += '<button data-audio="../inputs/' + e(block['recordingId']) + '.wav" data-start="' + str(block['start']) + '" data-label="' + e(label) + '">Listen</button>'
            out += '</p>'
        return out + '</details>'

    if index.get('speaker_annotations'):
        body += '<section><h2>Speaker role and relationship hypotheses</h2><p>Subjective AI confidence, not calibrated probability or confirmed credentials/ownership. Voice-clustering and turn-assignment errors can invalidate an otherwise plausible interpretation.</p>'
        markdown += ['## Speaker role and relationship hypotheses', '', 'Subjective AI confidence, not confirmed identities or calibrated probabilities.', '']
        for annotation in index['speaker_annotations']:
            label = annotation['speaker'] + ' — ' + annotation['role']
            body += '<h3>' + e(label) + '</h3><p>' + e(annotation['relationship']) + '</p><p>Model confidence: ' + e(round(annotation['confidence'], 2)) + '. ' + e(annotation['reason']) + '</p><p>Alternatives: ' + e('; '.join(annotation['alternatives'])) + '</p>' + evidence(annotation['evidence'])
            markdown += [label, annotation['relationship'], 'Model confidence: ' + str(annotation['confidence']), annotation['reason'], 'Alternatives: ' + '; '.join(annotation['alternatives']), 'Evidence: ' + '; '.join(ref['source'] + ': ' + ref['quote'] for ref in annotation['evidence']), '']
        body += '</section>'

    if not episodes:
        body += '<p>The whole-night context map has not been saved yet. Source transcripts are already available below.</p>'
    for number, episode in enumerate(episodes, 1):
        file = root / 'calls' / f'episode-{number:03d}.json'
        body += '<section><h2>' + str(number) + '. ' + e(episode['title']) + '</h2><p><strong>Patient:</strong> ' + e(episode['patient_label'] or 'Unassigned') + '; <strong>proposed association:</strong> ' + e(episode['association']) + '</p><p>' + e(episode['association_reason']) + '</p>'
        if episode['identity_evidence']:
            body += evidence(episode['identity_evidence'])
        hints = name_hints(episode, sources, aliases)
        if hints:
            body += '<details><summary>All matching name mentions to consider — not automatic patient links</summary><p>These source passages are retrieval candidates. The same spelling or owner-supplied alias does not prove the same patient.</p><ul>'
            for key in hints['literal_mention_blocks']:
                block = sources[key]
                body += '<li><a href="#' + e(key) + '">Recording ' + str(block['recordingNumber']) + ' · ' + e(f'{block["start"]:.2f}s') + '</a>' + (' — context-only ASR warning' if not block['eligible'] else '') + '</li>'
            body += '</ul></details>'
        markdown += ['## ' + str(number) + '. ' + episode['title'], '', 'Patient: ' + str(episode['patient_label'] or 'Unassigned') + ' — ' + episode['association'], episode['association_reason'], '']
        if not file.exists():
            failed = root / 'calls' / f'episode-{number:03d}-failure.json'
            body += ('<p class="warning">Detailed extraction failed after bounded retries; the index proposal and original transcript remain available.</p>' if failed.exists() else '<p>Detailed extraction pending; this is an index proposal only.</p>') + '</section>'; continue
        detail = load_json(file)['data']
        body += '<h3>Readable account — AI synthesis, check the evidence</h3><p>' + e(detail['summary']).replace('\n', '<br>') + '</p><p><strong>Association limitations:</strong> ' + e(detail['association_note']) + '</p>'
        if detail.get('summary_evidence'):
            body += evidence(detail['summary_evidence'])
        markdown += [detail['summary'], '', 'Association limitations: ' + detail['association_note'], '']
        for title, key in [('Recorded details and reasoning', 'facts'), ('Practical lessons and equipment', 'practical_lessons')]:
            if detail[key]:
                body += '<h3>' + title + '</h3>'; markdown += ['### ' + title, '']
            for item in detail[key]:
                prefix = item.get('kind', '')
                body += '<p>' + ('<strong>' + e(prefix) + ':</strong> ' if prefix else '') + e(item['text']) + '</p>'
                markdown += ['- ' + (prefix + ': ' if prefix else '') + item['text']]
                if item.get('limitations'):
                    body += '<p><em>Limitations:</em> ' + e(item['limitations']) + '</p>'
                    markdown += ['  Limitations: ' + item['limitations']]
                body += evidence(item['evidence'])
                markdown += ['  Evidence: ' + '; '.join(ref['source'] + ': ' + ref['quote'] for ref in item['evidence'])]
        body += '<h3>Unknowns and contradictions</h3><ul>' + ''.join('<li>' + e(u) + '</li>' for u in detail['uncertainties']) + '</ul>'
        markdown += ['', '### Unknowns and contradictions', *['- ' + u for u in detail['uncertainties']], '']
        if detail['study_questions']:
            body += '<h3>Study questions — unreviewed</h3>'; markdown += ['### Study questions', '']
        for question in detail['study_questions']:
            from .study_policy import question_answer, question_options
            options=question_options(question)
            option_lines=[x['id']+': '+x['text'] for x in options]
            body += '<details><summary>' + e(question['prompt']) + '</summary>'
            if options:body += '<ul>'+''.join('<li>'+e(line)+'</li>' for line in option_lines)+'</ul>'
            body += '<p><strong>Answer:</strong> ' + e(question_answer(question)) + '</p><p>' + e(question['explanation']) + '</p>' + evidence(question['evidence']) + '</details>'
            markdown += ['Q: ' + question['prompt'], *option_lines, 'A: ' + question_answer(question), question['explanation'], '']
            markdown += ['Evidence: ' + '; '.join(ref['source'] + ': ' + ref['quote'] for ref in question['evidence']), '']
        rejected = root / 'calls' / f'episode-{number:03d}-rejected.json'
        if rejected.exists():
            entries = load_json(rejected)
            if entries:
                body += '<p class="warning">' + str(len(entries)) + ' items failed citation validation and are excluded from the accepted facts/cards above. Raw model output is retained privately.</p>'
            for entry in entries:
                if entry.get('section') == 'summary':
                    body += '<details><summary>Unaccepted model narrative — source citations did not fully validate</summary><p class="warning">This is retained for human review, not accepted as a source-validated account. Compare the original transcripts and audio before trusting these statements.</p><p>' + e(entry['item']) + '</p></details>'
        repairs = root / 'calls' / f'episode-{number:03d}-repairs.json'
        if repairs.exists():
            body += '<p>' + str(len(load_json(repairs))) + ' source citations were deterministically restored using unique casing/spacing matches or an exact quote elsewhere in the same recording. No words or cross-recording links were guessed; original raw output is retained.</p>'
        body += '</section>'
    body += '<section id="sources"><h2>Complete source review</h2><p>' + str(len(used)) + '/' + str(eligible) + ' eligible source blocks cited in the current report. This is source coverage, not medical accuracy. Uncited and context-only text remains below; absence from a lesson does not mean it was unimportant.</p>'
    for record in recordings:
        body += '<details><summary>Recording ' + str(record['number']) + ': ' + e(record['name']) + ' — ' + e(record['status']) + '</summary>'
        if not record['blocks']:
            raw_file = root / 'transcription-details' / (record['id'] + '.json')
            body += '<p class="warning">No valid parsed transcript. Raw Whisper wording below is unvalidated and was not supplied as extraction evidence. Offsets are not repaired or invented.</p>'
            if (root / 'inputs' / (record['id'] + '.wav')).exists():
                body += '<button data-audio="../inputs/' + e(record['id']) + '.wav" data-start="0" data-label="Recording ' + str(record['number']) + '">Listen from recording start</button>'
            if raw_file.exists():
                for segment in load_json(raw_file).get('transcription', []):
                    body += '<p>' + e(segment.get('text', '')) + '</p>'
        for key in record['blocks']:
            block = sources[key]
            body += '<p id="' + e(key) + '"><strong>' + e(key) + ' · ' + e(f'{block["start"]:.2f}–{block["end"]:.2f}s') + '</strong> ' + e(block['text']) + '</p>'
            if block.get('speakerSegments'):
                body += '<p>Voice estimates: ' + e('; '.join(f"{s['startSeconds']:.2f}–{s['endSeconds']:.2f}s {s['speaker']}" for s in block['speakerSegments'])) + '</p>'
            if block.get('repeatExcludedSpans'):
                body += '<p class="warning">Contains repeated wording excluded from AI input. The original text above is retained for review.</p>'
            if (root / 'inputs' / (block['recordingId'] + '.wav')).exists():
                body += '<button data-audio="../inputs/' + e(block['recordingId']) + '.wav" data-start="' + str(block['start']) + '" data-label="Recording ' + str(block['recordingNumber']) + '">Listen at this source timestamp</button>'
        body += '</details>'
    body += '</section><section id="baseline"><h2>' + e(experiment.get('baselineLabel', 'Previous small-context output for comparison')) + '</h2><p>Saved records for comparison only; these were not edited or sent to the model as evidence. A historical library article may include older additions.</p>'
    baseline = load_json(root / 'baseline.json')
    for article in baseline['articles']:
        body += '<details><summary>' + e(article['title']) + '</summary><pre>' + e(article['body']) + '</pre></details>'
    for q in baseline['questions']:
        body += '<details><summary>Previous card: ' + e(q['prompt']) + '</summary><p>' + e(q.get('answer', '')) + '</p><p>' + e(q['explanation']) + '</p></details>'
    body += '</section>'
    sha = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
    csp = "default-src 'none'; style-src 'unsafe-inline'; media-src 'self'; script-src 'sha256-" + sha + "'; base-uri 'none'; form-action 'none'"
    document = '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="' + e(csp) + '"><title>Last night — larger-context review</title><style>body{max-width:1100px;margin:auto;padding:24px;font:17px/1.6 system-ui;background:#faf8f2;color:#18332f;overflow-wrap:anywhere}section{background:white;padding:20px;border:1px solid #bdcec2;border-radius:10px;margin:20px 0}details{padding:10px;border-left:3px solid #c5d7cc;margin:10px 0}summary,button{cursor:pointer}audio{width:100%}pre{white-space:pre-wrap}blockquote{border-left:3px solid #899e91;padding-left:14px;margin-left:6px}.warning{color:#793609}a{color:#12645c}button{padding:6px 12px;font:inherit}</style></head><body>' + body + '<script>' + SCRIPT + '</script></body></html>'
    folder = root / 'review'; folder.mkdir(exist_ok=True, mode=0o700)
    atomic_write(folder / 'shift-context.html', document)
    atomic_write(root / 'readable-notes.md', '\n'.join(markdown))
    return folder / 'shift-context.html'
