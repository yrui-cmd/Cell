# Pro customer API contract

This contract describes the deployed Pro customer API's submission, status, download, image verification and billing requirements. Skill creation and client mock tests are separate from a paid `cell_su8` drawing run.

Origin: `https://xiaomiao-ai.com`. Authentication: customer `Authorization: Bearer <Xiaomiao API Key>`, reusing SU7's Windows DPAPI or macOS Keychain entry. Never use the backend worker token or `/api/internal/no-ai-pro-jobs` routes.

| Action | Method and path | Result |
|---|---|---|
| Health | GET `/api/no-ai-pro-jobs/health` | Public API health only; does not prove worker availability |
| Live balance | GET `/api/balance` | HTTP200, `ok:true`, valid nonnegative numeric `available_credits`; at least 3 before every new upload |
| Submit | POST `/api/no-ai-pro-jobs` | multipart single `image`; HTTP201, actual `job_id`, frozen `cost`, `source_sha256`, `canvas_px`, `expires_at` |
| Status | GET `/api/no-ai-pro-jobs/<job_id>` | `received`, `processing`, `completed`, `failed` or `cancelled`; includes frozen `cost`; completed includes `result_sha256` |
| Download | GET `/api/no-ai-pro-jobs/<job_id>/result` | Valid PNG bytes; HTTP download filename is fixed as `final.png`; `X-Xiaomiao-Charged` 1 for first settlement, 0 for repeated downloads |
| Cancel | DELETE `/api/no-ai-pro-jobs/<job_id>` | Only for an explicit cancellation request; not automatic cleanup |

The bundled CLI exposes health, balance, process and resume. Cancellation is a documented API operation, not a CLI subcommand.

IDs use `wm_` plus20 lowercase hexadecimal characters. Construct the same job's fixed customer URLs; do not follow response-provided external URLs or redirects. Do not replay a POST on connection loss. A saved known job is polled/downloaded with the same identity and key.

Input: valid single-frame PNG/JPEG/WebP, at most32MiB and40,000,000pixels. Result: valid single-frame PNG, at most64MiB and40,000,000pixels, SHA matching `result_sha256`, width/height equal to the EXIF-corrected visible input dimensions. Verify the returned PNG's actual dimensions and full layout before continuing. A successful response or download does not verify removal of every hidden watermark.

Billing for new jobs is 3 credits: reserved at upload, settled on first customer result download. Unconsumed reservations are released on failure, cancellation or expiry. Each stage has its own 24-hour validity window: queue expiry is calculated from submission, processing lease expiry is recalculated from claim, and result download expiry is recalculated from completion. Repeated downloads and repeated result returns with the same SHA do not extend the existing expiry. Read the latest `expires_at` while receiving. Missing/invalid balances are unavailable, never inferred. Downloaded result billing headers and real balance responses are recorded separately.

`X-Xiaomiao-Charged: 1` is a first-settlement flag, not the number of credits. It means this job's frozen cost was settled; `0` means a repeat download with no new settlement. Historical 1-credit and 5-credit jobs keep their original cost and reservation when resumed or downloaded. The client records the actual job cost in its state, receipt and summary and does not rewrite an existing completed receipt.

New client submissions require `--approved-three-credits` (Python: `approved_three_credits=True`) and a live balance of at least 3. The obsolete `--approved-one-credit` and `--approved-five-credits` cannot authorize a new job. Existing task directories resume without reauthorization, a new preflight balance check or another POST. If a submission ACK supplies a cost different from the authorized 3, the client saves its real job ID and reported cost and stops at `pricing_mismatch` for manual reconciliation. A subsequent status cost differing from the job's frozen cost also stops; neither case authorizes resubmission. Health exposes the current `cost_per_image` without charging.

HTTP401/403 indicates authorization failure;402 insufficient credits;404 missing/expired;409 not ready/state conflict;413 size limit;415 invalid raster;422 dimension mismatch;503 temporary service failure. Continue bounded status/download reads for the same existing job on transient connection errors. Terminal failure/expiry stops receipt; it never starts a replacement paid job.

The unchanged SU7 vector recognition upload limit is10MiB. A valid Pro result can exceed it. Preserve such a result, mark it incompatible for recognition, and report the limit; do not silently compress, change canvas coordinates or regenerate to hide it.

The bundled Pro client needs Python3 and Pillow for image decoding. Windows credentials use the existing `%USERPROFILE%/.codex/secrets/xiaomiao-api-key.dpapi`; macOS uses Keychain service `cell-ppt-xiaomiao`. Existing setup helpers configure these securely. No key belongs inside this skill, its reports or its examples.
