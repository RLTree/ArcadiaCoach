# Phase 10 – Assessment Attachment UX & Agent Ingestion (October 13, 2025)

## Scope Recap
- Replace the metadata-driven attachment hack with a structured `attachments` field on assessment submissions.
- Give learners a first-class macOS workflow to upload reference files or register support links before submitting their onboarding assessment.
- Persist uploaded assets, surface them across developer/pro profile APIs, and feed attachment context into the automated grading payload.

## Backend Updates
- Added `assessment_attachments.py`, a JSON-backed store that manages pending uploads (`POST /api/onboarding/{username}/assessment/attachments/*`), persists files under `app/data/assessment_attachments/`, and exposes download routes for both pending and archived submissions.
- Extended `AssessmentSubmission` with a structured `attachments` list (`AssessmentSubmissionAttachment`), updated `submission_store.record()` to consume pending uploads, and hydrated payloads via the new store while preserving metadata fallbacks for legacy data.
- Introduced REST endpoints to list, upload (multipart), link, delete, and download assessment attachments; developer resets now purge attachment artifacts alongside profile/submission state.
- Enriched grading inputs so `_payload_for_agent` carries attachment metadata (ids, kinds, sizes, URLs) allowing GPT-based graders to ingest learner-provided context when generating feedback.
- Backfilled regression coverage in `backend/tests/test_assessment_submission_store.py` to exercise the new workflow: file/link upload, submission auto-association, download responses, and developer reset cleanup.

## macOS Client Updates
- Created a dedicated attachment manager in `OnboardingAssessmentFlow` with file picker (via `NSOpenPanel`), link entry sheet, removal actions, and real-time pending state sourced from `AppViewModel.pendingAssessmentAttachments`.
- Added `BackendService` helpers (`list/upload/delete/createAssessmentAttachment*`) that wrap the new endpoints and reuse the shared JSON decoder.
- Expanded `AssessmentSubmissionRecord.Attachment` with ids, MIME/type hints, file sizes, and relative download URLs; dashboards/detail views now render attachment sizes and resolve backend-relative links automatically.
- Wired `AppViewModel` to orchestrate attachment lifecycle (refresh, upload, link creation, deletion) and cleared pending state after successful submissions or developer resets.

## Follow-ups / Open Items
1. Surface inline file previews (syntax-highlight snippets or image thumbnails) inside the attachment manager once the rendering pipeline is ready (Phase 19 accessibility tooling).
2. Capture attachment ingestion telemetry (success/failure, file types) and alerting hooks as part of Phase 23 agent operations.
3. Evaluate encrypting the stored attachment directory ahead of Phase 17 persistence migration to maintain parity once we move to the database-backed store.
4. Add SwiftUI snapshot tests for the new attachment manager and detail panels when UI testing infra lands (tracked for Phase 20 QA work).

## Validation Checklist
1. `uv run pytest backend/tests/test_assessment_submission_store.py`
2. `swift test`
3. Manual flow:
   - Start the onboarding assessment, upload a file and register a link via the macOS attachment panel; verify they appear in the pending list with size and link metadata.
   - Submit the assessment and confirm the dashboard history + detail view show the structured attachments with working download links.
   - Hit `/api/onboarding/{username}/assessment/attachments` before submission (expect pending items) and after submission (expect empty list).
   - Download the stored file via `/api/onboarding/{username}/assessment/attachments/{attachment_id}/download` and confirm parity with the uploaded binary.
