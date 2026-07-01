# Mobile Map Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the mobile-first map interface for the meeting point recommender.

**Architecture:** Preserve backend/API behavior and refactor only the frontend presentation. Add a small pure view-model helper module for testable state mapping, then rebuild `App.jsx` around mobile map states and replace the old desktop CSS.

**Tech Stack:** React 19, Vite, lucide-react, browser MediaRecorder, existing FastAPI backend.

---

### Task 1: View Model Helpers

**Files:**
- Create: `frontend/src/mobileViewModel.js`
- Create: `frontend/src/mobileViewModel.test.js`

- [ ] Add Node test coverage for state mapping, progress steps, and candidate display.
- [ ] Implement helpers used by `App.jsx`.
- [ ] Run `node --test src/mobileViewModel.test.js`.

### Task 2: Mobile App Structure

**Files:**
- Modify: `frontend/src/App.jsx`

- [ ] Replace desktop two-column layout with map-first mobile shell.
- [ ] Keep existing recording, reset, upload, history, and playback handlers.
- [ ] Add ready, processing, result, correction, and history overlay sections.

### Task 3: Mobile Styling

**Files:**
- Replace: `frontend/src/styles.css`

- [ ] Apply map-first mobile visual system.
- [ ] Style bottom sheets, processing steps, result cards, candidates, correction state, and history overlay.
- [ ] Keep responsive desktop behavior as a centered phone-like canvas.

### Task 4: Verification

**Commands:**
- `cd frontend && node --test src/mobileViewModel.test.js`
- `cd frontend && npm run build`
- Start backend and frontend, then inspect `http://localhost:5177/`.

**Expected:** tests and build pass; UI renders all major states without text overlap at mobile and desktop viewport widths.
