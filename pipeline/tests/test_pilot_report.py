import base64
import re
from pathlib import Path
import wave

import pytest

from vet_pipeline.pilot_report import render_pilot
from vet_pipeline.util import digest_file, write_json


def pilot(tmp_path):
    root = tmp_path / 'private-pilot'
    samples = []
    for label in ['earlier', 'later']:
        folder = root / label
        (folder / 'audio').mkdir(parents=True)
        for name in ['original', 'normalized']:
            with wave.open(str(folder / 'audio' / (name + '.wav')), 'wb') as f:
                f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000); f.writeframes(b'\0' * 64000)
        write_json(folder / 'session.json', {'originalSha256': digest_file(folder / 'audio/original.wav'), 'normalizedSha256': digest_file(folder / 'audio/normalized.wav')})
        write_json(folder / 'transcript.json', {'segments': [{'start': .5, 'end': 1.5, 'text': '<script>synthetic uncertain observation</script>'}]})
        samples.append({'label': label, 'sourceName': '<unsafe>.wav', 'sourceStartSeconds': 120, 'quality': {}})
    write_json(root / 'pilot.json', {'samples': samples})
    return root


def test_audio_is_embedded_and_all_links_stay_inside_single_file(tmp_path):
    root = pilot(tmp_path)
    report = render_pilot(root).read_text()
    clips = re.findall('src="data:audio/wav;base64,([^"]+)"', report)
    assert len(clips) == 2
    assert base64.b64decode(clips[0]) == (root / 'earlier/audio/normalized.wav').read_bytes()
    assert all(link.startswith('#') for link in re.findall('href="([^"]+)"', report))
    assert 'file://' not in report and 'http://' not in report and 'https://' not in report
    assert 'data-start="0.5"' in report
    assert '&lt;script&gt;synthetic' in report
    assert "script-src &#x27;sha256-" in report


def test_changed_source_is_not_embedded(tmp_path):
    root = pilot(tmp_path)
    (root / 'earlier/audio/normalized.wav').write_bytes(b'changed')
    with pytest.raises(ValueError, match='audio changed'):
        render_pilot(root)
    assert not (root / 'index.html').exists()


def test_report_rejects_git_workspace(tmp_path):
    root = pilot(tmp_path)
    (root / '.git').mkdir(); (root / '.git/HEAD').write_text('ref: refs/heads/main\n')
    with pytest.raises(ValueError, match='outside every Git'):
        render_pilot(root)


def test_labels_cannot_escape_pilot_root(tmp_path):
    root = pilot(tmp_path)
    write_json(root / 'pilot.json', {'samples': [{'label': '../other'}]})
    with pytest.raises(ValueError, match='Invalid pilot label'):
        render_pilot(root)


def test_single_file_export_works_outside_hidden_source_directory(tmp_path):
    root = pilot(tmp_path)
    output = tmp_path / 'private-view/standalone.html'
    assert render_pilot(root, output) == output
    assert output.is_file() and (output.stat().st_mode & 0o777) == 0o600
    assert output.read_text().count('data:audio/wav;base64,') == 2
