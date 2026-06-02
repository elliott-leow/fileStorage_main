# AI Agent Guide — Using the File Server API

This document tells an AI agent (or any program) how to **browse, search, read,
and write files** on this server over HTTP. Every browse/search endpoint can
return clean JSON, so you never have to parse HTML.

> **TL;DR for agents**
> - List a folder: `GET /<path>?format=json`
> - Semantic search: `GET /<path>?smart_query=<q>&format=json`
> - Download a file: `GET /<path>`  (raw bytes)
> - Upload a file: `POST /upload/<path>` with header `X-Upload-Key` and the raw body
> - Everything returns JSON when you send `?format=json` or `Accept: application/json`.

## Base URL

```
http://<host>:8000
```

On the reference deployment the server runs on a Raspberry Pi reachable over
Tailscale (e.g. `http://raspberrypi:8000` or `http://100.x.y.z:8000`). Replace
`<host>` with your address. All examples below use `$BASE`.

```bash
BASE=http://raspberrypi:8000
```

## Authentication model

The server is key-based (no user accounts). There are several keys, set as
environment variables on the server; an agent is given whichever it needs:

| Key | Env var | Used for |
|-----|---------|----------|
| Upload key | `KEY` | uploads, create folder, set protection, shortcuts, rebuild index |
| Delete key | `DELETE_KEY` | deleting files/folders |
| Hidden key | `HIDDEN_KEY` | hiding/unhiding folders, viewing hidden folders |
| Folder key | (per folder) | accessing a specific password-protected folder |
| Master key | (in `folder_keys.json`) | unlock everything for a session; dashboard |

Keys are passed either as an HTTP header (`X-Upload-Key`, `X-Delete-Key`) or in
the JSON body (`"key": "..."`), depending on the endpoint (noted per-endpoint).
**Reading and listing public folders needs no key.** Protected folders require a
session unlock (see *Protected folders* below).

---

## Reading

### List a directory (JSON)

```bash
curl "$BASE/classes/BME221_BIOCHEM/?format=json"
```

Response:

```json
{
  "path": "classes/BME221_BIOCHEM",
  "is_search": false,
  "query": null,
  "breadcrumbs": [{"name": "Home", "url": "/"}, {"name": "classes", "url": "/classes"}, ...],
  "count": 12,
  "entries": [
    {
      "name": "01_DNA_Replication.pdf",
      "path": "classes/BME221_BIOCHEM/01_DNA_Replication.pdf",
      "type": "file",                // "file" | "dir" | "shortcut"
      "size": "2.1 MB",
      "size_bytes": 2201234,
      "modified": "2024-09-25 14:02",
      "modified_ts": 1727280120.0,
      "protected": false,
      "hidden": false,
      "url": "/classes/BME221_BIOCHEM/01_DNA_Replication.pdf"
    }
  ]
}
```

Use each entry's `url` to download it. The root listing is `GET /?format=json`.

### Semantic (smart) search

Searches **file contents** (PDF/text/markdown) with embeddings + BM25 +
cross-encoder reranking, and personalizes by your browsing trajectory. Returns
ranked results with a plain-text `snippet` and a `score` (0–1).

```bash
curl "$BASE/?smart_query=enzyme%20kinetics%20michaelis%20menten&format=json"
```

```json
{
  "is_search": true, "query": "enzyme kinetics michaelis menten", "count": 8,
  "entries": [
    {"name": "enzymes.md", "path": "study/biochem/enzymes.md", "type": "file",
     "url": "/study/biochem/enzymes.md", "score": "0.91",
     "snippet": "...Michaelis-Menten kinetics, Km and Vmax, competitive inhibition..."}
  ]
}
```

Tip: smart search is global (searches the whole tree from root). Results are
already ranked best-first; there is no pagination — raise specificity to narrow.

### Filename search

```bash
curl "$BASE/?search=final&recursive=true&format=json"
```

Matches names (not contents). `recursive=true` searches subfolders; scope it by
putting a path before the query: `GET /docs/?search=report&format=json`.

### Download a file

```bash
curl -O "$BASE/classes/BME221_BIOCHEM/01_DNA_Replication.pdf"   # raw bytes
```

- Add `?download=1` to force an attachment, or `?preview=1` for inline preview
  (the server logs a `preview` event instead of an `open`).

### Download a folder as a zip

```bash
curl -OJ "$BASE/api/download-folder?path=classes/BME221_BIOCHEM"
```

### List only subdirectories (JSON)

```bash
curl -X POST "$BASE/api/list-dirs" -H "Content-Type: application/json" \
  -d '{"path": "classes"}'
# -> {"subdirs": [{"name": "BME221_BIOCHEM", "is_protected": false}, ...], "current_path": "classes"}
```

---

## Writing

### Upload a file (streaming)

`POST /upload/<destination/path/filename>` with the raw file as the body and the
upload key in `X-Upload-Key`. Intermediate folders are created automatically.

```bash
curl -X POST "$BASE/upload/notes/2026/lecture1.pdf" \
  -H "X-Upload-Key: $UPLOAD_KEY" --data-binary @lecture1.pdf
# -> 201 {"status": "success", "filename": "notes/2026/lecture1.pdf"}
```

Upload to a protected folder using that folder's key instead of the global key.

### Create a folder

```bash
curl -X POST "$BASE/api/create-folder" -H "Content-Type: application/json" \
  -d '{"parent_path": "notes", "folder_name": "2026", "key": "'"$UPLOAD_KEY"'",
       "protection_password": null}'
```

Set `protection_password` to password-protect the new folder.

### Delete files/folders

```bash
curl -X POST "$BASE/api/delete-items" -H "Content-Type: application/json" \
  -H "X-Delete-Key: $DELETE_KEY" \
  -d '{"items_to_delete": ["notes/old.txt", "notes/2025"]}'
# -> {"success_count": 2, "fail_count": 0, "errors": []}
```

### Other write endpoints

| Endpoint | Body | Key |
|----------|------|-----|
| `POST /api/set-path-protection` | `{path, password, key}` | upload key |
| `POST /api/toggle-hidden` | `{path, key, hide}` | hidden key |
| `POST /api/create-shortcut` | `{name, location, target, key}` | upload key |
| `POST /api/delete-shortcut` | `{name, location, key}` | upload key |
| `POST /rebuild-index` | — (header `X-Upload-Key`) | upload key |

---

## Protected folders

A protected folder returns `403`/`requires_key` until unlocked **for the
session**. Unlock by POSTing the folder key to `/validate-key`, keeping the
session cookie:

```bash
curl -c jar.txt -X POST "$BASE/validate-key" -H "Content-Type: application/json" \
  -d '{"path": "private", "key": "'"$FOLDER_KEY"'"}'
# then reuse the cookie:
curl -b jar.txt "$BASE/private/?format=json"
```

`POST /validate-master-key {"key": ...}` unlocks all protected + hidden folders
for the session at once.

---

## Utility

```bash
curl "$BASE/health"                       # disk usage + status JSON
curl -b jar.txt "$BASE/api/analytics/summary"   # usage analytics (needs dashboard unlock)
```

## Minimal Python client

```python
import requests
BASE = "http://raspberrypi:8000"
s = requests.Session()

def ls(path=""):       return s.get(f"{BASE}/{path}", params={"format": "json"}).json()["entries"]
def search(q):         return s.get(f"{BASE}/", params={"smart_query": q, "format": "json"}).json()["entries"]
def read(path):        return s.get(f"{BASE}/{path}").content
def upload(path, data, key): return s.post(f"{BASE}/upload/{path}", data=data, headers={"X-Upload-Key": key})

for hit in search("dna replication telomere")[:5]:
    print(hit["score"], hit["path"], "—", hit.get("snippet", "")[:80])
```

## Notes & conventions

- Paths are forward-slash, relative to the served root; no leading slash needed
  in `?format=json` requests (`GET /a/b/?format=json`).
- Listings are returned in full (no pagination); folders are typically modest.
- `type` is `dir`, `file`, or `shortcut`. Shortcuts point elsewhere (`url` is the
  target). Directories have `size_bytes: -1`.
- Smart search requires the content index; build/refresh it with
  `POST /rebuild-index`. Without it, only filename search works.
- All activity (searches, folder views, opens) is logged locally for the
  analytics dashboard; nothing leaves the server.
