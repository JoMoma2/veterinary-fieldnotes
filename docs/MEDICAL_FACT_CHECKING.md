# Independent medical checks for study questions

A transcript citation establishes that a statement was recorded. It does not establish medical truth. Every real question must now pass a separate external-reference check before publication, in addition to the existing owner/privacy approval. Publication approval cannot bypass this gate. Synthetic test fixtures remain synthetic demonstrations; they never count as independently verified medical material.

The optional automatic stage runs after extraction and local saving, using the existing local Ollama model in a separate request. It sees only the proposed study material and retrieved public-reference excerpts—not the shift transcript, case archive or earlier extraction reasoning. This is source independence, not a guarantee that the same local model can adjudicate every medical issue correctly. Automated source corroboration is not clinical certification.

The checker assesses question premises, the correct/model answer, explanation and every possible distractor/choice. It distinguishes supported, contradicted, ambiguous and insufficient evidence. Every supported or contradicted component needs an exact quotation from a supplied external reference. Missing components, invented citations or mismatched quotations fail closed. Drug comparisons must respect the actual comparator, species, route, formulation and endpoint. Dose potency, intrinsic efficacy, receptor affinity, sedation and clinical analgesia are different claims.

Raw recordings, transcripts and case facts are preserved. Suggested corrections remain separate from the original question and are not automatically applied or published. A revised question gets a new content hash and requires a new check. No unsupported claim is silently repaired in the clinical archive.

## Reference library and privacy

References live outside Git in a private JSON directory. An operator explicitly selects public HTTPS document URLs on trusted medical/veterinary/regulatory/manufacturer hosts. Import supports HTML, text and PDF using an existing `pdftotext` binary; no driver/model installation is needed. Redirects to untrusted/private hosts and access-denial pages are refused. No authentication/paywall bypass, private uploads, generated web queries or external inference calls are made. The local model has no web-search tool.

```bash
cd ~/FieldNotes/app
pipeline/.venv/bin/python scripts/check-study-questions.py import-url \
  --url https://www.fda.gov/AN-EXPLICIT-PUBLIC-REFERENCE \
  --title 'Reference title' --scope 'Actual species/formulation/clinical scope' \
  --directory ~/FieldNotes/data/medical-references
```

Import only legitimate reference documents. Titles/scope help navigate evidence; they are not themselves medical evidence. Documents retain source URL, retrieval date, body/download hashes and prior versions. Phrase retrieval weights distinctive terms and limits repeated excerpts from the same document, reducing the risk that generic paragraphs hide the actual comparison reference. These mechanical safeguards do not prove semantic entailment.

**This initial source library is curated, not unrestricted automatic medical research.** Questions outside its coverage remain pending/insufficient. Expand it with appropriate authorized references. Optional weekly refresh fetches only previously selected URLs; it never sends a question, patient name, transcript or recording to a search service. Unavailable refreshes preserve old cache data. Aged or changed reference sets invalidate checks rather than silently passing stale evidence.

## Configure and run

```toml
[question_verification]
enabled = true
references_dir = "~/FieldNotes/data/medical-references"
auto_refresh_sources = true
refresh_days = 7
max_reference_age_days = 180
reference_char_limit = 14000
max_output_tokens = 32768
max_attempts = 2
timeout_seconds = 1800
```

```bash
pipeline/.venv/bin/python scripts/check-study-questions.py run \
  --workspace /PRIVATE/WORKSPACE --config /PRIVATE/pipeline.toml
# Display-only refresh, no model call:
pipeline/.venv/bin/python scripts/check-study-questions.py report --workspace /PRIVATE/WORKSPACE
# A bounded explicit recheck after improving retrieval/references or revising a candidate:
pipeline/.venv/bin/python scripts/check-study-questions.py run \
  --workspace /PRIVATE/WORKSPACE --config /PRIVATE/pipeline.toml \
  --force --question-id QUESTION_ID
```

The default automatic stage is disabled for other installations until references/local inference are configured. The real-question publication requirement is unconditional. Existing owner profiles can enable the stage without changing global Ollama settings. Requests use the configured model/context and a short request-scoped keep-alive, with existing shared-GPU admission safeguards. Resource deferral consumes no attempt; the standalone command returns 75 so systemd can retry. Invalid output is bounded and held, not treated as a medical verdict. Completed checks survive restart, and new questions do not require retranscription or extraction to be repeated.

## Review and publication

Morning Review has an **Independent medical fact-checking report** with original answers, component verdicts, reasons, minimal reference quotations, source links/dates and proposed revisions. Its loopback view reads current results without inference, so refresh while checks run. The extraction view explicitly labels its old questions as unverified drafts. The normal private processing archive continues to save even if no question can be verified.

Proof records are private sidecars under `question-verification/`, bound to the complete candidate hash, current reference-set hashes, policy version and reference age. Changing wording/answer/explanation, editing/removing references, or aging evidence requires a new check. Medical support does not grant publication or clinical-cloud-storage permission. Exported, independently supported real questions include external reference titles/URLs in the explanation; private proof data and clinical provenance remain private.

The initial whole-shift adapter still produces flashcards. The verifier also checks all answer options for the website's other question formats. Zero publishable questions is an acceptable result when medical support is inadequate.
