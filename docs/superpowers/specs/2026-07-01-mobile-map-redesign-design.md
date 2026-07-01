# Mobile Map Redesign Design

## Goal

Refactor the current desktop-style meeting point prototype into a mobile-first map utility based on the Stitch prototype, while preserving the existing recording, upload, history, map, and TTS behavior.

## Product Direction

The app should feel like a focused single-task tool: open it, say where both people are, review the recommended meeting point, then play the answer or try another input. The map is the primary visual layer. Bottom sheets carry input, progress, results, alternatives, and correction states.

## States

- Ready: map background, current location marker, prompt, example sentence, voice button, manual input affordance, history entry.
- Recording/Ready to upload: same shell, with timer and recording preview/submit action.
- Processing: softened map context plus explicit steps: ASR, extracting locations, Amap recommendation, voice generation.
- Result: real map with markers, bottom result sheet with title, address, distance, route-time placeholders, recommendation reason, voice playback, alternatives, and re-record.
- Correction: shown when request fails or no result is available after upload, with error message, extracted location if any, and retry/manual controls.
- History: lightweight overlay opened from the top-right history button, reusing existing history API data.

## Implementation Constraints

- Keep the existing API contract and `AmapPanel` integration.
- Do not use Stitch's static Tailwind HTML directly.
- Do not add bottom tab navigation or hamburger menu in the first implementation.
- Current backend does not reliably provide per-person route duration; display placeholders or existing duration data without inventing precise values.
- Keep changes focused to the frontend.

## Acceptance Criteria

- The app renders as a mobile-first map interface at phone width.
- Existing recording, upload, TTS playback, and history selection still work.
- `uploading` shows processing steps.
- Successful results show map, recommendation, reasons, candidates, and actions.
- Errors provide a correction/retry path instead of only a plain alert.
