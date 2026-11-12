# Source handoff

For current machine state, permissions, quarantine locations and unfinished operational work, read the private hub `~/FieldNotes/SESSION_HANDOFF.md`. This document intentionally contains no real-session artifacts or capability links. Older source history describes superseded experiments.

The selected local lineup is Parakeet TDT v3 + Silero VAD and Qwen3.8 27B. Normal ingestion now supports the selected native ASR backend; whole-shift extraction supports the pinned native template, reasoning/stream settings and tested decoding parameters. See NIGHTLY_WHOLE_SHIFT.md for the configuration contract. Settings do not start services or grant upload/publication consent.

Current services, recorder authorization, retained archives, publication permissions
and actual test results are recorded only in the private handoff. Historical cleanup
pauses and comparison workers are not current operating instructions. Never revive
an archived worker or relabel an old model-run proof after a code change.

The public application checkout contains source, tests, synthetic fixtures and only
screened educational exports. Canonical clinical records, identities and raw model
outputs stay outside source Git. Public patient aliases and the optional local
study researcher are described in PUBLIC_PRIVACY_STUDY.md. Source changes do not
automatically grant activation, cloud storage or publication permission.

Useful references: AGENTS.md, LOCAL_LAYOUT.md, NIGHTLY_WHOLE_SHIFT.md, MEDICAL_FACT_CHECKING.md, USB_AUTOMATION.md, OPERATIONS.md. Historical benchmark documents describe their own model/runtime snapshots, not the active selected profile.
