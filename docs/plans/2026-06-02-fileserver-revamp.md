# File Server Revamp Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Revamp the Flask file server — Catppuccin self-hosted UI, hybrid+rerank semantic search, SQLite activity analytics with a trajectory-based `P(file|path)` navigation model, an analytics dashboard, UX upgrades, and dead-code removal — all running on a Raspberry Pi 5.

**Architecture:** Keep the existing app-factory + blueprints + services layout. Add three services (`analytics_service`, `navigation_service`, reworked `search_service`), wire best-effort logging into routes, and replace the Tailwind CDN with a hand-written Catppuccin CSS design system. Pure-logic pieces (BM25, RRF, sessionization, navigation math, config parsing) are TDD'd with `pytest`; model/UI integration is verified by running the app.

**Tech Stack:** Python 3.13/3.14, Flask, `sentence-transformers` (`BAAI/bge-small-en-v1.5`, `cross-encoder/ms-marco-MiniLM-L-6-v2`), numpy, `pypdf`, stdlib `sqlite3`, hand-rolled BM25 (no `rank_bm25`), vanilla JS + inline-SVG charts. Drops `scikit-learn`.

---

## Conventions

- Tests live in `tests/`, run with `python -m pytest tests/ -v`.
- Each logic task: write failing test → run (fails) → implement → run (passes) → commit.
- UI/integration tasks: implement → run app / curl → verify → commit.
- Commit messages: `feat:`, `fix:`, `refactor:`, `test:`, `chore:`; trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Best-effort logging must NEVER raise into a request (wrap in try/except).

---

## Phase 0 — Setup

### Task 0.1: Test harness + gitignore
**Files:** Create `tests/__init__.py`, `tests/conftest.py`, `pytest.ini`; Modify `.gitignore`, `requirements.txt`.

- `.gitignore`: add `analytics.db`, `*.db`, `tests/.tmp/`, `__pycache__/`, `*.pyc`, `server.log`, `semantic_index*.pkl`.
- `requirements.txt`: remove `scikit-learn`; add `pytest>=8` under a dev section (commented import note); keep torch, sentence-transformers, pypdf, numpy, Flask, humanize, python-dotenv.
- `conftest.py`: fixture `app` (TestingConfig pointing `PUBLIC_DIR` at a temp tree with a few sample `.txt`/`.md` files), fixture `client`.
- **Verify:** `python -m pytest -q` collects 0 tests, exits clean.
- **Commit:** `chore: add pytest harness and tighten gitignore`.

---

## Phase 1 — Cleanup & config fixes (make it smaller)

### Task 1.1: Remove legacy upload page
**Files:** Delete `templates/upload.html`; Modify `app/routes/main.py` (drop `/upload-ui` route + `upload_ui()`), `app/services/file_service.py` (drop `get_all_directories()`).
- Grep to confirm no remaining refs: `grep -rn "upload-ui\|upload.html\|get_all_directories" app templates static`.
- **Verify:** `python -c "from app import create_app; create_app()"` OK.
- **Commit:** `refactor: remove unreachable standalone upload page (~650 lines)`.

### Task 1.2: Remove unused path utils
**Files:** Modify `app/utils/path_utils.py` (delete `get_safe_path`, `get_parent_path`, `join_paths`), `app/utils/__init__.py` (fix exports).
- **Verify:** `python -c "from app import create_app; create_app()"` OK; grep shows no refs.
- **Commit:** `refactor: drop unused path utilities`.

### Task 1.3: Config fixes (TDD)
**Files:** Modify `app/config.py`; Test `tests/test_config.py`.
- Behavior: `SECRET_KEY` = `FLASK_SECRET_KEY` or `FLASK_SECRET` or insecure default; `FOLDER_KEYS_CONFIG_FILE` = `FOLDER_KEYS_CONFIG` or `FOLDER_KEY` or `folder_keys.json`. Add `ANALYTICS_ENABLED` (default true), `ANALYTICS_DB` (`analytics.db`), `SESSION_IDLE_TIMEOUT_MIN` (30), `SEARCH_RERANK_MODEL` (`cross-encoder/ms-marco-MiniLM-L-6-v2`), default `SEMANTIC_MODEL` → `BAAI/bge-small-en-v1.5`, add `.md`/`.markdown` to `SUPPORTED_EXTENSIONS`.
- **Test:** monkeypatch env `FLASK_SECRET=abc` → `Config` picks it up; `is_secret_key_secure()` true.
- **Commit:** `fix: read FLASK_SECRET/FOLDER_KEY env aliases; add analytics+search config`.

### Task 1.4: run.py threaded
**Files:** Modify `run.py` → `app.run(..., threaded=True)`.
- **Commit:** `perf: serve with threaded=True so search doesn't block downloads`.

---

## Phase 2 — Analytics service (SQLite)

### Task 2.1: Schema + connection (TDD)
**Files:** Create `app/services/analytics_service.py`, `tests/test_analytics.py`.
- `AnalyticsService(db_path, enabled, idle_timeout_min)`:
  - lazy `_connect()` (one sqlite3 connection per thread via `check_same_thread=False` + a `threading.Lock`, `PRAGMA journal_mode=WAL`).
  - `_init_db()` creates `events(id INTEGER PK, ts REAL, session_id INTEGER, type TEXT, path TEXT, query TEXT, meta TEXT)` and `sessions(id INTEGER PK, started_ts REAL, last_ts REAL, client TEXT)`, plus indexes on `events(type)`, `events(session_id)`, `events(path)`.
- **Test:** constructing on a temp path creates tables (`sqlite_master` query).
- **Commit:** `feat(analytics): sqlite schema and connection`.

### Task 2.2: Sessionization + log() (TDD)
- `log(type, path=None, query=None, meta=None, client=None, now=None)`:
  - find latest session for `client`; if none or `now - last_ts > timeout`, create a new session; else reuse and update `last_ts`.
  - insert event; best-effort (swallow + log exceptions). `now` injectable for tests.
- **Tests (inject `now`):** two events 1 min apart → same `session_id`; events 40 min apart → different sessions; different `client` → different sessions; `enabled=False` → no rows.
- **Commit:** `feat(analytics): sessionized event logging`.

### Task 2.3: Aggregation queries (TDD)
- Methods returning plain dicts/lists: `top_files(limit, type='open')`, `searches_over_time(days)`, `top_queries(limit)`, `top_folders(limit)`, `folder_transitions(limit)` (consecutive `navigate` pairs within a session), `recent_activity(limit)`, `totals()`, `file_popularity()` → `{path: {count, last_ts}}` for the search booster.
- **Tests:** seed events with injected `now`, assert each aggregate.
- **Commit:** `feat(analytics): dashboard + ranking aggregations`.

### Task 2.4: Wire into app + routes
**Files:** Modify `app/__init__.py` (init `app.analytics_service`, pass config), `app/routes/main.py` (log `navigate` on dir view, `search` on each search, `open` on file serve — all best-effort, `client` = flask `session` sid or a cookie), `app/routes/api.py` (add `POST /api/analytics/event` for `preview`; validate `type` allowlist), startup log line.
- Helper `_client_id()` (stable per-browser id stored in flask session).
- **Verify (curl):** hit `/`, download a file, run a search → rows appear in a temp DB.
- **Commit:** `feat(analytics): log navigate/open/search/preview from routes`.

---

## Phase 3 — Navigation model `P(file | path)`

### Task 3.1: Name normalization + folder embeddings (TDD)
**Files:** Create `app/services/navigation_service.py`, `tests/test_navigation.py`.
- `normalize_name(s)`: split camelCase, replace `_-.` with space, split digit/letter boundaries, lowercase, collapse spaces (`"BME221_BIOCHEM"` → `"bme221 biochem"`).
- `NavigationService(search_service, analytics_service)` holds a `{folder_path: embedding}` map built from the index's folder set (lazy; reuse `search_service` encoder). Encodings L2-normalized.
- **Test:** `normalize_name` cases (pure unit, no model).
- **Commit:** `feat(nav): name normalization + folder-name embedding map`.

### Task 3.2: Context embedding from trajectory (TDD with fake encoder)
- `context_embedding(trajectory)`: trajectory = ordered list of visited folder paths (+ flags). Recency-weighted mean (exp decay, newest highest); detect backtracking (navigating to an ancestor of an earlier folder) → down-weight the abandoned folder. Return normalized vector (or None if empty).
- Inject a **fake encoder** (maps known names → fixed unit vectors) so the math is deterministic and model-free.
- **Tests:** recency weighting orders correctly; backtracked folder contributes less; empty → None.
- **Commit:** `feat(nav): recency/backtrack-weighted context embedding`.

### Task 3.3: P_hist co-occurrence (TDD)
- `historical_scores(trajectory)`: from `analytics_service` sessions, aggregate `visited_folder → folder_of_opened_file` counts; given current visited folders, produce `{folder: prob}` then map to a per-file prior via the file's parent folder. Normalize.
- **Tests:** seed sessions where visiting `A` led to opening files in `B`; assert `B`-folder files get higher `P_hist`.
- **Commit:** `feat(nav): historical folder→target co-occurrence prior`.

### Task 3.4: Blend `P(file|path)` (TDD)
- `file_priors(trajectory, candidate_paths)` → `{path: score in [0,1]}` = `α·P_hist + (1−α)·P_nl`, where `P_nl(file)=cosine(context_emb, folder_name_emb(file))` and `α=min(0.7, history_strength)`. Files with no signal → 0.
- **Tests:** with fake encoder + seeded history, the "study"-like folder ranks above an unrelated folder given an "mcat"-like trajectory; deterministic.
- **Commit:** `feat(nav): blended P(file|path) prior`.

---

## Phase 4 — Search service rework

### Task 4.1: BM25 (TDD, standalone)
**Files:** Create `app/services/bm25.py`, `tests/test_bm25.py`.
- Compact `BM25(corpus_tokens, k1=1.5, b=0.75)` with `tokenize(text)` (lowercase, `\w+`), `get_scores(query_tokens) -> np.ndarray`.
- **Tests:** doc containing the query term scores > a doc without; idf reduces weight of ubiquitous terms.
- **Commit:** `feat(search): hand-rolled BM25`.

### Task 4.2: RRF fusion (TDD)
**Files:** Create `app/services/fusion.py`, `tests/test_fusion.py`.
- `rrf(rankings: list[list[int]], k=60) -> list[(idx, score)]` sorted desc.
- **Tests:** item ranked high in both lists beats item high in only one; stable.
- **Commit:** `feat(search): reciprocal rank fusion`.

### Task 4.3: Index format v2 (store text) + chunk overlap
**Files:** Modify `app/services/search_service.py`.
- Bump index to store per-chunk `text`; embeddings stored L2-normalized float32; `_chunk_text` gains overlap (e.g. 500-word window, 80-word stride). `_validate_index` checks new shape + presence of `text`. Add `.md` extraction.
- **Verify:** build over the test tree; index dict has `embeddings`, `metadata[i].text`.
- **Commit:** `feat(search): index v2 with chunk text + overlap; add markdown`.

### Task 4.4: bge model + normalized matmul retrieval (drop sklearn)
- `_load_model` lazy (first use); query instruction prefix for bge; `_semantic_rank(query)` = normalized query · normalized matrix (numpy), returns ranked indices. Remove all sklearn usage.
- **Verify:** `search_service.is_available` true after first call; a known query retrieves the seeded doc.
- **Commit:** `feat(search): bge-small embeddings, numpy cosine, no sklearn`.

### Task 4.5: Cross-encoder rerank (lazy)
- `_rerank(query, candidate_chunk_idxs)` loads cross-encoder on first use, scores `(query, text[:1024chars])`, returns reordered. Guard if model unavailable → skip gracefully.
- **Verify:** rerank reorders a small candidate set sensibly.
- **Commit:** `feat(search): cross-encoder reranking (lazy)`.

### Task 4.6: Orchestrated `search()` with snippets + personalization
- New `search(query, top_n=15, trajectory=None, popularity=None) -> [{path, score, snippet, components}]`:
  1. semantic_rank + BM25 → RRF top ~30 candidate chunks.
  2. rerank → ordered chunks; collapse to best chunk per file.
  3. `final = w_r·norm(rerank) + w_p·popularity_recency + w_t·P(file|path)` (weights in config; default `0.7/0.15/0.15`).
  4. build `snippet` from best chunk (window around top query term, `<mark>` highlight, escaped).
- **Tests:** snippet builder (pure) highlights terms and escapes HTML; fusion+collapse dedupes by file.
- **Commit:** `feat(search): hybrid+rerank with snippets and personalization`.

### Task 4.7: Wire search into routes
**Files:** Modify `app/routes/main.py` (`_handle_smart_search` passes current `trajectory` (from analytics current session) + `popularity` (from `analytics_service.file_popularity()`); attach `snippet` to entry info), `app/__init__.py` (construct `NavigationService`, give `SearchService` access or pass priors in route).
- **Verify (curl):** `?smart_query=...` returns results; with a seeded trajectory the order changes.
- **Commit:** `feat(search): trajectory + popularity aware smart search`.

---

## Phase 5 — Backend for UX + dashboard

### Task 5.1: Breadcrumb data + sort + preview flag
**Files:** Modify `app/routes/main.py`.
- Pass `breadcrumbs=[{name,url}]` built from `current_path`. Pass `entries` with raw `size_bytes` + `mtime_ts` for client sort. Files served inline-previewable: keep `send_from_directory` (browser handles inline for pdf/img/txt via `Content-Disposition: inline` when `?preview=1`).
- **Commit:** `feat(ui): breadcrumb + sort metadata + inline preview param`.

### Task 5.2: Dashboard route + summary API
**Files:** Modify `app/routes/main.py` (`GET /dashboard` gated by master/upload key via a small key-check; render `dashboard.html`), `app/routes/api.py` (`GET /api/analytics/summary` → all aggregates as JSON; gate likewise).
- **Verify (curl):** unauthorized → prompts/401; authorized → JSON.
- **Commit:** `feat(dashboard): route + analytics summary API`.

---

## Phase 6 — Frontend (Catppuccin, drop CDN)

### Task 6.1: `app.css` design system
**Files:** Create `static/css/app.css`; delete old `static/css/styles.css` (fold needed rules in).
- Catppuccin Mocha (`.dark`, default) + Latte (`:root`) variables → semantic tokens; component classes (`.btn*`, `.card`, `.input`, `.modal*`, `.toolbar`, `.file-row`, `.badge`, `.breadcrumb`, `.chart*`, `.spinner`) + minimal layout helpers. Mobile-friendly.
- **Commit:** `feat(ui): self-hosted Catppuccin CSS design system`.

### Task 6.2: Rewrite `index.html` + `error.html`
**Files:** Modify both. Remove CDN `<script>`; inline pre-paint theme snippet in `<head>`; replace Tailwind utility classes with component classes; add breadcrumb bar, sort controls, preview-aware links, snippet rendering, keep all data-* hooks JS relies on.
- **Verify:** load `/` in both themes; no `cdn.tailwindcss.com` ref remains.
- **Commit:** `feat(ui): Catppuccin index + error templates`.

### Task 6.3: Rewrite `partials/modals.html`
**Files:** Modify. Same class migration; add a `previewModal` (iframe/img/pre container).
- **Commit:** `feat(ui): Catppuccin modals + preview modal`.

### Task 6.4: JS updates
**Files:** Modify `static/js/theme.js` (Catppuccin icons, pre-paint), `static/js/file-browser.js` (sort handlers, keyboard shortcuts `/ Esc ↑ ↓ Enter`, click-to-preview that opens previewModal + logs `preview` via `/api/analytics/event`, breadcrumb is plain links); `static/js/modals.js` unchanged or minor. Create `static/js/dashboard.js` if summary API used client-side (else server-render).
- **Verify:** shortcuts, sorting, preview, upload modal still work.
- **Commit:** `feat(ui): sort, shortcuts, click-to-preview, theme polish`.

### Task 6.5: `dashboard.html` with inline-SVG charts
**Files:** Create `templates/dashboard.html`.
- Server-rendered cards: totals; top files (bar); searches/day (sparkline/bar); top queries; top folders; folder→folder transitions (flow list); recent activity feed. Helper Jinja macros for SVG bars. Catppuccin themed.
- **Verify:** `/dashboard` renders with seeded data.
- **Commit:** `feat(dashboard): Catppuccin analytics dashboard with SVG charts`.

---

## Phase 7 — Models + index

### Task 7.1: Preinstall models
- Script/inline: `python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; SentenceTransformer('BAAI/bge-small-en-v1.5'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"` (uses HF cache). Confirm load on CPU.
- **Verify:** both load without error; note approx RAM.

### Task 7.2: Build real index
- Start app (or call build) to index `public/`; confirm embeddings count and that a real query returns sensible files + snippets.
- **Commit:** (index file is gitignored) `chore: document index build`.

---

## Phase 8 — End-to-end verification

### Task 8.1: Full smoke test (REQUIRED SUB-SKILL: superpowers:verification-before-completion)
- `python -m pytest tests/ -v` all green.
- Boot app; `curl` matrix: `/` (+breadcrumb), file download (`open` logged), `?search=`, `?smart_query=` (snippets, ranked), `/health`, `/dashboard` (auth + render), `/api/analytics/summary`, `/api/analytics/event` (preview logged).
- Inspect `analytics.db`: sessions formed, events grouped; craft a trajectory → smart-search order changes (P(file|path) effective).
- Visual: Mocha + Latte correct; no CDN ref; no FOUC.
- **Commit:** `test: end-to-end verification notes` (+ README updates).

### Task 8.2: Docs + README
- Update `README.md`: new search pipeline, analytics + dashboard, removed upload page, config aliases, model preinstall, no-sklearn.
- **Commit:** `docs: README for revamped search, analytics, dashboard`.

---

## Risks & mitigations
- **Hand-written CSS parity** — verify both themes visually; keep data-* hooks intact.
- **Cross-encoder latency on Pi** — lazy load, cap candidates (30) + text length; `threaded=True`.
- **Model RAM** — bge (~130 MB) + cross-encoder (~90 MB) + torch; 8 GB is ample; both lazy.
- **Analytics never breaks requests** — all logging best-effort in try/except.
- **Index size from storing chunk text** — acceptable for 598 docs; monitor pickle size.
