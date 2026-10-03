# Plain Terms – Frontend

> Legal agreements, explained in plain language.

Plain Terms is a web app that analyses Terms of Service, EULAs and Privacy Policies and returns short plain-language summaries with risk flags (High / Medium / Low).

---

## How to run

### Option A — Open directly in a browser (no install needed)
Node.js was not detected on this machine, so the app is built as a **self-contained CDN-based React + Tailwind app** that needs no build step.

1. Open `frontend/index.html` in any modern browser (Chrome, Firefox, Edge, Safari).
2. That's it. All dependencies (React 18, ReactDOM, Tailwind CSS, Babel standalone) load from CDN on first open.

> ⚠ The Babel standalone JSX transform adds a ~200 ms startup cost. For production, migrate to Option B.

### Option B — Vite dev server (requires Node.js ≥ 18)
When Node.js is available:

```bash
cd frontend
npm install
npm run dev        # development server at http://localhost:5173
npm run build      # production build → dist/
npm run preview    # preview the production build
```

> The `package.json` is included but the Vite project files (`vite.config.js`, `src/main.jsx`, etc.) are stubs ready to be expanded. The current working app is `index.html`.

---

## File structure

```
frontend/
├── index.html              ← Complete working app (CDN React + Tailwind)
├── package.json            ← npm metadata + scripts (for future Vite migration)
├── README.md               ← This file
└── src/
    ├── api.js              ← API layer: simplify(input) returns mock data
    │                          Replace the body with a real fetch() when backend is ready
    ├── mock/
    │   ├── clauses.json    ← 10 realistic mock clauses
    │   ├── sampleTexts.js  ← Sample agreement excerpts for the dropdown
    │   └── translations.js ← UI strings + clause-level translations (EN/HI/ML)
    └── (components would go here in a Vite project)
```

---

## Screens

| Screen | How to reach |
|---|---|
| **Input** | Default on load |
| **Results** | Click "Simplify" (or load a sample, then Simplify) |
| **Overlay** | Click "Side-by-side view" on the Results screen |
| **Language** | Dropdown in the header — works on all screens |

---

## Mock data shape (`src/mock/clauses.json`)

Each clause object:

```json
{
  "id": 1,
  "heading": "Broad License to Your Content",
  "text": "original clause text…",
  "summary": "plain-language explanation…",
  "risk_level": "high | medium | low",
  "category": "Data collection | Third-party sharing | Auto-renewal | Cancellation | Liability | Other",
  "company": "Generic | Netflix | WhatsApp | …"
}
```

---

## API contract (`src/api.js`)

```js
import { simplify } from './src/api.js';

const result = await simplify(inputText);
// result: { clauses: Clause[], counts: { high, medium, low, total } }
```

Replace the `setTimeout` mock with a `fetch('/api/simplify', { method:'POST', body:inputText })` when the backend is ready.

---

## Language support

| Language | Code | UI strings | Clause translations |
|---|---|---|---|
| English | `en` | ✅ Full | ✅ All 10 clauses |
| Hindi | `hi` | ✅ Full | ✅ Clauses 1–2 (demo) |
| Malayalam | `ml` | ✅ Full | ✅ Clauses 1–2 (demo) |

For clauses without a translation the app shows: *"⚠ Translation unavailable for this clause."*

---

## Assumptions made during development

1. **No Node.js on the machine.** The app was built as a CDN-based single-file React app. A `package.json` is provided for future migration to Vite.
2. **Mock data only.** `simplify()` always returns the same 10 clauses regardless of input. Real analysis will require a backend.
3. **URL field is disabled.** The spec asked for a URL input field; it is rendered but disabled with "coming soon" since there is no backend to fetch and parse URLs yet.
4. **Overlay clause matching uses heuristics.** The left-panel paragraph highlighting matches clauses by checking if a paragraph contains words from the clause heading or first few words of the clause text. This is approximate.
5. **Translation stubs for clauses 3–10.** The spec required mock translations for "two or three clause summaries". Clauses 1 and 2 have full Hindi and Malayalam translations; all others show "Translation unavailable".
6. **No routing library.** The four screens are managed with a single `screen` state variable since there is no bundler available to add React Router.
7. **Colour is never the only indicator.** Every risk badge includes an icon (⚠ High, ◉ Medium, ✓ Low) and a text label to meet the accessibility requirement.
8. **sources.csv and .md files outside frontend/ were not touched.** All work is confined to `frontend/`.
