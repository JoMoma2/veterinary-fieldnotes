from vet_pipeline.speaker_transcripts import decision, windows, POLICY


def test_owner_requires_independent_reference_support_and_negative_veto():
    templates=[{'vector':[1,0]}]*3
    assert decision([1,0],templates,[[0,1]],.55)['ownerCandidate']
    assert not decision([1,0],templates,[[1,0]],.55)['ownerCandidate']
    assert not decision([0,1],templates,[[0,1]],.55)['ownerCandidate']
    assert not decision([1,0],templates[:2],[],.55)['ownerCandidate']


def test_short_and_overlapping_turns_abstain_and_all_audio_offsets_remain():
    turns=[{'start':0,'end':18,'localSpeaker':0},{'start':4,'end':6,'localSpeaker':1}]
    rows=list(windows(turns,18,POLICY))
    assert [r['end']-r['start'] for r in rows[:3]]==[8,8,2]
    assert not rows[0]['eligible'] and rows[1]['eligible'] and not rows[2]['eligible']
    assert not rows[3]['eligible']


def test_transcript_report_preserves_words_and_times_and_escapes_source_text(tmp_path):
    from vet_pipeline.speaker_transcripts import render
    from vet_pipeline.util import write_json
    root=tmp_path/'isolated';root.mkdir();visible=tmp_path/'visible'
    write_json(root/'session.json',{'visible':str(visible)})
    write_json(root/'progress.json',{'status':'running','completed':0,'recordings':2})
    write_json(root/'recordings.json',[{'id':'test','number':1,'name':'example.wav'}, {'id':'missing','number':2,'name':'missing.wav'}])
    write_json(root/'transcripts/test.json',{'segments':[{'start':1.25,'end':4.5,'text':'Original <script>alert(1)</script> wording'}]})
    write_json(root/'transcription-details/missing.json',{'transcription':[{'text':'Raw <unverified> words'}]})
    render(root)
    page=(visible/'Results.html').read_text();markdown=(visible/'Transcript.md').read_text()
    assert '&lt;script&gt;alert' in page and '<script>alert(1)' not in page
    assert '1.25–4.50s' in markdown and 'Original <script>alert(1)</script> wording' in markdown
    assert 'No usable saved parsed transcript' in page
    assert 'Raw &lt;unverified&gt; words' in page and 'Raw <unverified> words' in markdown
    assert 'timing and speakers unassigned' in page
    assert not (root/'transcripts/missing.json').exists()
    assert not (root/'jobs.sqlite3').exists()
