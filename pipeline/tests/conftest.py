import pytest
from vet_pipeline.store import Store
from vet_pipeline.config import config
from vet_pipeline.util import REPO
from vet_pipeline.ingest import ingest


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "private")
    yield s
    s.close()


@pytest.fixture
def cfg():
    return config()


@pytest.fixture
def first(store):
    return ingest(
        store,
        REPO / "fixtures/pipeline/transcripts/01-first.json",
        "s-2026-10-22",
        "2026-10-22",
        "synthetic",
        "test",
    )[0]
