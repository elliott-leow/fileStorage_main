# File Server Revamp — Design

**Date:** 2026-06-02
**Status:** Approved (brainstorming complete)
**Target hardware:** Raspberry Pi 5 (8 GB RAM, 4× Cortex-A76, arm64), Python 3.13/3.14
**Users:** 1–2 (private home file server)
**Content:** ~12 GB, 1,547 files, 598 PDFs/txt

## Goals (from the user)

1. Optimize the codebase; make it **smaller** where possible (remove dead code).
2. UI / aesthetic revamp, **Catppuccin Mocha** for dark mode (Latte for light).
3. **Smarter search** with modern transformers that still run on the Pi.
4. **Activity analytics**: log searches, navigation trajectories, and file opens to a database.
5. Use access patterns + **navigation trajectories** to improve search ranking — `P(file | path)`.
6. An **analytics dashboard**.
7. **Preinstall the models** and **test everything end-to-end**.

## Decisions (locked during brainstorming)

| Topic | Decision |
|-------|----------|
| Theming | Drop the Tailwind Play CDN; ship a self-hosted Catppuccin CSS design system (offline, no FOUC). |
| Search | Modern embedding model + hybrid (semantic + BM25) + cross-encoder rerank + snippets + personalization. |
| Legacy upload page | Remove `templates/upload.html`, `/upload-ui`, `get_all_directories()`. |
| UX additions | Breadcrumbs, click-to-preview, sort controls, keyboard shortcuts. |
| Dashboard auth | Gate `/dashboard` behind master key if configured, else upload key. |
| Models | `BAAI/bge-small-en-v1.5` + `cross-encoder/ms-marco-MiniLM-L-6-v2`; preinstall to `CACHE_DIR`. |

---

## 1. Theming — self-hosted Catppuccin CSS

- Remove `<script src="https://cdn.tailwindcss.com">` from all templates.
- New `static/css/app.css`:
  - **Palette variables**: Catppuccin **Mocha** under `.dark` (default), **Latte** under `:root`.
  - **Semantic tokens**: `--bg`, `--surface`, `--surface2`, `--overlay`, `--text`, `--subtext`,
    `--muted`, `--accent`, `--accent-hover`, `--danger`, `--success`, `--warning`, plus file-type
    icon hues (`--icon-folder`, `--icon-pdf`, `--icon-image`, `--icon-file`, `--icon-shortcut`).
  - **Component classes**: `.btn`, `.btn-icon`, `.btn-primary/-danger/-ghost`, `.card`, `.input`,
    `.checkbox`, `.modal-overlay`, `.modal`, `.toolbar`, `.file-row`, `.badge`, `.breadcrumb`,
    `.chart-bar`, `.spinner`. Keep a tiny set of layout helpers (`.row`, `.col`, `.grow`, `.muted`).
- Rewrite `index.html`, `partials/modals.html`, `error.html`; new `dashboard.html`.
- `theme.js`: set `.dark` before first paint (inline head snippet) to avoid FOUC; toggle persists to `localStorage`.
- Net effect: one small CSS file replaces a ~300 KB in-browser compiler; fully offline.

**Risk:** faithfully reproducing the current layout by hand. Mitigation: verify visually in both modes.

## 2. Smarter search (`app/services/search_service.py` rework)

**Pipeline:** `query → embed + BM25 → RRF fusion → cross-encoder rerank → +personalization → snippets`.

- **Embedding model:** `BAAI/bge-small-en-v1.5` (384-d). bge query instruction
  (`"Represent this sentence for searching relevant passages: "`) prepended to queries only.
  Lazy-loaded on first search (keeps startup fast, RAM free until used).
- **Index:** stored as a pickle in `CACHE_DIR`. Per chunk store: `path`, `chunk_index`,
  `text` (for BM25 + snippets), and the embedding (float32, L2-normalized). Add `.md`/`.markdown`
  to supported extensions. Chunking gains a small overlap (sliding window).
- **Semantic retrieval:** normalized embeddings → single numpy matmul (cosine = dot product).
  **This removes the `scikit-learn` dependency.**
- **Keyword retrieval:** compact hand-rolled **BM25** over chunk tokens (no new dependency).
- **Fusion:** Reciprocal Rank Fusion (RRF, `k=60`) of semantic + BM25 rankings → top ~30 candidates.
- **Rerank:** `cross-encoder/ms-marco-MiniLM-L-6-v2` scores `(query, chunk_text)` for the 30,
  truncated to ~256 tokens → top 15. Lazy-loaded.
- **Snippets:** return the best chunk per file, truncated around matched terms, terms highlighted.
- **Personalization:** blend the analytics signal (§4/§5) into the final score:
  `final = w_rerank·rerank + w_pop·popularity_recency + w_traj·P(file | path)`.

**Latency budget on Pi 5:** embedding query ~tens of ms; BM25 trivial; cross-encoder ~1–2 s for 30
short pairs. Acceptable, lazy-loaded, runs on a worker thread (`run.py` → `threaded=True`).

## 3. Cleanup / make it smaller

- Delete `templates/upload.html` (621 lines), the `/upload-ui` route + `upload_ui()`, and
  `FileService.get_all_directories()`.
- Delete unused `path_utils` helpers: `get_safe_path`, `get_parent_path`, `join_paths`; fix
  `app/utils/__init__.py` exports.
- Remove `scikit-learn` from `requirements.txt`; add nothing new for BM25/analytics (stdlib `sqlite3`).
- **Config fixes:** `config.py` reads `FLASK_SECRET` **or** `FLASK_SECRET_KEY`, and `FOLDER_KEY`
  **or** `FOLDER_KEYS_CONFIG`, so the existing `.env` actually applies (today the secret key and
  folder-keys path are silently ignored). `run.py` → `threaded=True`.
- (Already deleted in working tree: `serve_public_modern.py`, `search_index.py`.)

## 4. Analytics (`app/services/analytics_service.py`, SQLite — no new dependency)

- DB file `analytics.db` (gitignored). Two tables:
  - `events(id, ts, session_id, type, path, query, meta)` — `type ∈ {search, navigate, open, preview}`.
  - `sessions(id, started_ts, last_ts)` — a **navigation session** = events grouped by idle timeout
    (default 30 min). `session_id` assigned at log time by comparing to the last event's `ts`
    (also keyed by Flask session cookie to separate concurrent users).
- **Server-side logging** (robust, no JS needed):
  - directory view → `navigate(path)`
  - file served → `open(path)`
  - search executed → `search(query, meta={mode, result_count})`
  - `POST /api/analytics/event` for client-only `preview` events.
- Config flag `ANALYTICS_ENABLED` (default true). Writes are best-effort (never break a request).

## 5. Navigation model — `P(file | path)` (`app/services/navigation_service.py`)

Given the **current session trajectory** (ordered folders visited before the search), score candidate
files by likelihood of being the target, blending two signals:

1. **Historical co-occurrence** (learned from the user's own past sessions):
   - From completed sessions, aggregate `folder_visited → target_folder_of_opened_file` counts.
   - `P_hist(file) ∝ Σ_over visited folders f  count[f → folder(file)]`, normalized.
   - **Backtracking handling:** when the trajectory navigates to an ancestor of a previously visited
     folder, the abandoned subtree is marked a negative signal (down-weighted) — "went back" means
     that branch was wrong.
2. **Natural-language priors** (semantic; works cold-start, no history needed):
   - Precompute, during index build, an embedding for each folder (and file) **name**, normalized
     (`BME221_BIOCHEM` → `"bme221 biochem"`, split camelCase/underscores/digits).
   - Build a **recency-weighted context embedding** = weighted mean of visited folders' name
     embeddings (exponential decay; recent visits dominate; backed-out folders down-weighted).
   - `P_nl(file) ∝ cosine(context_emb, name_emb(file's folder))`.
   - This yields the example behavior: visiting **mcat** raises **study** because the names embed close.

**Blend:** `P(file | path) = α·P_hist + (1−α)·P_nl` (α grows with how much history exists).
Used as the `w_traj` term in §2. Folder→folder transition stats also feed a **navigation-flow**
visualization on the dashboard. Optional: a lightweight "you might be looking for…" hint on the
current folder driven by the same model (secondary; search boost is the primary deliverable).

## 6. Dashboard (`/dashboard`)

- Auth: master key if configured, else upload key (reuses existing key-prompt modal pattern).
- Server-rendered `dashboard.html` + `GET /api/analytics/summary` (JSON) for any dynamic bits.
- **Dependency-free inline SVG / CSS charts** (consistent with "drop the CDN"): 
  - top accessed files, searches over time (last 30 days), top queries, most-visited folders,
    top folder→folder transitions (navigation flow), recent-activity feed, headline totals.
- Catppuccin-themed.

## 7. UX upgrades

- **Breadcrumbs:** clickable path (`Home / classes / BME221 / …`) replacing the lone "Parent" link.
- **Click-to-preview:** PDFs, images, and text open inline (modal/inline viewer) with an explicit
  download button; a preview logs a `preview` event.
- **Sort controls:** by name / size / modified, asc/desc (client-side on the rendered list).
- **Keyboard shortcuts:** `/` focus search, `Esc` close/clear, `↑/↓` move selection, `Enter` open.

## Data flow

```
request → route → auth/visibility checks → file_service / search_service
        → analytics_service.log(event, session)        (best-effort)
        → navigation_service (search ranking boost)
        → template (app.css, Catppuccin)
```

## Models — preinstall

- Warm both models into `CACHE_DIR` ahead of time:
  `BAAI/bge-small-en-v1.5` (~130 MB) and `cross-encoder/ms-marco-MiniLM-L-6-v2` (~90 MB).
- After install, build the semantic index over `public/` so first search is instant.

## Testing & verification (must pass before "done")

1. `python -c "from app import create_app; create_app()"` boots with **no** errors/warnings about
   the secret key (config fix working).
2. Models import + load on CPU; `search_service.is_available` is true; index builds over `public/`.
3. `curl` smoke tests: `/` listing, breadcrumb nav, a file download (logs `open`), filename search,
   smart search returns ranked results **with snippets**, `/health`, `/dashboard` (auth), 
   `/api/analytics/summary` returns aggregates, `/api/analytics/event` records a preview.
4. Analytics: after the smoke tests, `analytics.db` contains `search`/`navigate`/`open` rows grouped
   into sessions; a crafted trajectory measurably reorders smart-search results (`P(file|path)` works).
5. Visual: Catppuccin Mocha (dark) and Latte (light) render correctly; no references to
   `cdn.tailwindcss.com` remain; no FOUC.
6. Run the app for real and exercise the flows before claiming completion.

## Out of scope / non-goals

- Multi-user accounts/ACLs beyond the existing key system.
- Production WSGI deployment (kept on `app.run`, now `threaded=True`); gunicorn remains documented.
- Heavyweight client JS chart libraries (using inline SVG instead).

## Net "smaller" accounting

Removed: legacy upload page (~621), `/upload-ui` + helper, unused path utils, `scikit-learn` dep,
(already-removed monolith + old index script). Added: lean `app.css`, reworked search, analytics +
navigation services, dashboard. Goal: leaner **core**, with new capabilities kept tight.
