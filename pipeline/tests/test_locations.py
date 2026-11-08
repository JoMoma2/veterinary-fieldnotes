from pathlib import Path
from vet_pipeline.locations import fieldnotes_home, location


def test_default_locations_keep_data_outside_source_checkout(monkeypatch, tmp_path):
    monkeypatch.delenv('FIELDNOTES_HOME', raising=False)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    assert fieldnotes_home() == tmp_path / 'FieldNotes'
    assert location('data', 'library') == tmp_path / 'FieldNotes/data/library'
    assert location('config', 'pipeline.toml') == tmp_path / 'FieldNotes/config/pipeline.toml'


def test_explicit_home_is_resolved_for_portable_install(monkeypatch, tmp_path):
    monkeypatch.setenv('FIELDNOTES_HOME', str(tmp_path / 'custom'))
    assert location('ai') == tmp_path / 'custom/ai'


def test_registrations_live_in_hub_and_preserve_owner_customizations(monkeypatch, tmp_path):
    import pytest
    from vet_pipeline.recorder_setup import install_registration
    monkeypatch.setenv('FIELDNOTES_HOME', str(tmp_path / 'hub'))
    index = tmp_path / 'systemd'; index.mkdir()
    target = index / 'vet-fieldnotes.service'
    target.write_text('same owner settings')
    install_registration(target, 'same owner settings', 'systemd')
    assert target.is_symlink()
    assert target.resolve() == tmp_path / 'hub/config/systemd/vet-fieldnotes.service'
    install_registration(target, 'same owner settings', 'systemd')
    with pytest.raises(ValueError, match='owner settings'):
        install_registration(target, 'changed settings', 'systemd')
    assert target.read_text() == 'same owner settings'


def test_desktop_registration_replaces_link_with_native_copy(monkeypatch, tmp_path):
    import pytest
    from vet_pipeline.recorder_setup import install_registration
    monkeypatch.setenv('FIELDNOTES_HOME', str(tmp_path / 'hub'))
    stored=tmp_path/'hub/config/desktop/review.desktop'
    stored.parent.mkdir(parents=True);stored.write_text('current command')
    target=tmp_path/'applications/review.desktop'
    target.parent.mkdir();target.symlink_to(stored)
    install_registration(target,'current command','desktop')
    assert not target.is_symlink()
    assert target.read_text()==stored.read_text()=='current command'
    install_registration(target,'current command','desktop')
    with pytest.raises(ValueError,match='owner settings'):
        install_registration(target,'different command','desktop')


def test_old_paths_work_without_any_filesystem_shortcuts(monkeypatch, tmp_path):
    from vet_pipeline.locations import local_path
    from vet_pipeline.private import private_path
    from vet_pipeline.util import load_json, digest_file
    from vet_pipeline.config import config
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.delenv('FIELDNOTES_HOME', raising=False)
    target = tmp_path / 'FieldNotes/data/evaluations/frozen'; target.mkdir(parents=True)
    old = tmp_path / '.local/share/vet-fieldnotes-evaluations/frozen'
    original = '{"provider":{"tokenizer_path":"' + str(tmp_path / '.local/share/vet-fieldnotes-ai/tokenizer.json') + '"}}'
    (target / 'experiment.json').write_text(original)
    assert not old.exists()
    assert private_path(old) == target
    assert local_path(old / 'experiment.json') == target / 'experiment.json'
    assert load_json(old / 'experiment.json')['provider']['tokenizer_path'].startswith(str(tmp_path / '.local'))
    assert digest_file(old / 'experiment.json') == digest_file(target / 'experiment.json')
    assert (target / 'experiment.json').read_text() == original
    cfg = tmp_path / 'FieldNotes/config'; cfg.mkdir()
    (cfg / 'pipeline.toml').write_text('[provider]\nmodel="fixture"\n')
    assert config(tmp_path / '.config/vet-fieldnotes/pipeline.toml')['provider']['model'] == 'fixture'
    assert local_path(tmp_path / '.local/share/vet-fieldnotes-ai-unrelated/test') == tmp_path / '.local/share/vet-fieldnotes-ai-unrelated/test'
    assert local_path('relative/path') == Path('relative/path')


def test_relocated_private_path_still_rejects_git_checkout(monkeypatch, tmp_path):
    import pytest
    from vet_pipeline.private import private_path
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.delenv('FIELDNOTES_HOME', raising=False)
    repo = tmp_path / 'FieldNotes/app'; (repo / '.git').mkdir(parents=True)
    (repo / '.git/HEAD').write_text('ref: refs/heads/main')
    with pytest.raises(ValueError, match='outside every Git'):
        private_path(tmp_path / 'vet-knowledge-library/private')


def test_legacy_path_resolution_does_not_invalidate_saved_request_identity(monkeypatch, tmp_path):
    import json
    from vet_pipeline.locations import local_path
    from vet_pipeline.util import load_json
    from vet_pipeline.shift_context import request_fingerprint
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    monkeypatch.delenv('FIELDNOTES_HOME', raising=False)
    old = tmp_path / '.local/share/vet-fieldnotes-ai/tokenizer.json'
    model = tmp_path / 'FieldNotes/ai/tokenizer.json'; model.parent.mkdir(parents=True)
    model.write_text('{}')
    experiment = {'provider': {'tokenizer_path': str(old)}, 'version': 1, 'gpuLayers': 1, 'modelDigest': 'unchanged'}
    before = request_fingerprint('same source evidence', experiment)
    saved = tmp_path / 'experiment.json'; saved.write_text(json.dumps(experiment))
    restored = load_json(saved)
    assert local_path(restored['provider']['tokenizer_path']).read_text() == '{}'
    assert not old.exists()
    assert request_fingerprint('same source evidence', restored) == before
    assert restored['provider']['tokenizer_path'] == str(old)
