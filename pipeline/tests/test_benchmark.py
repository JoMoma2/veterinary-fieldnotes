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
