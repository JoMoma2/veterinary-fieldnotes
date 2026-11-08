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
