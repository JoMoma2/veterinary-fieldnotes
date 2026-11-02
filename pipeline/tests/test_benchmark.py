import json
import pytest
from vet_pipeline.audio_benchmark import parse_whisper_cpp, word_error_rate
from vet_pipeline.benchmark import benchmark, score_output
from vet_pipeline.util import REPO


def test_extraction_benchmark_exercises_sequential_updates_and_records_resources(
    cfg, tmp_path
):
    files = [
        REPO / "fixtures/pipeline/transcripts" / name
        for name in ["01-first.json", "02-followup.json", "03-workaround.json"]
    ]
    report = benchmark(cfg, files, tmp_path / "benchmark.json")
    assert all(r["valid"] for r in report["results"])
    assert report["results"][1]["retrievedContextIds"]
    assert all(
        r["consolidation"]["earlierArticleTextPreserved"] for r in report["results"]
    )
    assert all(
        r["consolidation"]["caseCountMatchesExpectation"] for r in report["results"]
    )
    assert report["results"][0]["hardwareUtilization"]["sampleCount"] >= 2
    assert not any(r["hallucination_review_flags"] for r in report["results"])


def test_completeness_screen_does_not_count_copied_quotes():
    data = {
        "discussions": [
            {
                "account": "Unknown",
                "conclusions": "Unknown",
                "facts": [],
                "quotes": [{"text": "essential observation"}],
            }
        ],
        "articles": [],
        "cases": [],
    }
    assert score_output(data, {"must_capture": ["essential observation"]})[
        "missed_markers"
    ] == ["essential observation"]


def test_rejected_benchmark_response_retains_diagnostics(cfg, tmp_path, monkeypatch):
    from vet_pipeline.extraction import Provider
    from vet_pipeline.util import load_json

    response = load_json(REPO / "fixtures/pipeline/responses/first.json")
    response["discussions"][0]["quotes"][0]["text"] = "Invented evidence"

    def infer(self, *args):
        self.last_metrics = {"eval_count": 123}
        return response

    monkeypatch.setattr(Provider, "extract", infer)
    report = benchmark(
        cfg,
        [REPO / "fixtures/pipeline/transcripts/01-first.json"],
        tmp_path / "rejected.json",
    )
    row = report["results"][0]
    assert row["valid"] is False
    assert row["output"] == response
    assert row["providerMetrics"]["eval_count"] == 123
    assert row["inferenceSeconds"] >= 0


def test_hallucination_screen_flags_invented_known_outcome_and_diagnosis():
    data = {
        "discussions": [],
        "articles": [],
        "cases": [{"diagnosis": "invented", "outcome": None}],
    }
    flags = score_output(data, {"must_remain_unknown": ["diagnosis", "outcome"]})[
        "hallucination_review_flags"
    ]
    assert flags == ["Unexpected non-null case diagnosis"]


def test_audio_scoring_and_cpp_offsets():
    assert word_error_rate("one two three", "one three") == pytest.approx(1 / 3)
    assert word_error_rate("Feline, CASE.", "feline case") == 0
    parsed = parse_whisper_cpp(
        {
            "transcription": [
                {"offsets": {"from": 1200, "to": 3200}, "text": "Synthetic speech"}
            ]
        }
    )
    assert parsed["segments"][0]["start"] == 1.2
    with pytest.raises(ValueError):
        parse_whisper_cpp(
            {
                "transcription": [
                    {"offsets": {"from": 3200, "to": 1200}, "text": "Invalid"}
                ]
            }
        )


def test_synthetic_corpus_pcm_is_compatible_with_16khz_whisper_cli():
    from array import array
    from vet_pipeline.synthetic_audio import resample_pcm16_mono

    source = array("h", [1000] * 22050).tobytes()
    converted = resample_pcm16_mono(source, 22050)
    assert len(converted) == 16000 * 2
    assert all(v == 1000 for v in array("h", converted))
    with pytest.raises(ValueError):
        resample_pcm16_mono(b"bad", 22050)
