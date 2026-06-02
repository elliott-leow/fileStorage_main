"""
Hybrid semantic search with cross-encoder reranking.

Pipeline:  query -> (bge embeddings + BM25) -> reciprocal rank fusion
           -> cross-encoder rerank -> blend popularity + P(file|path) -> snippets

Models are lazy-loaded on first use so startup stays fast and RAM stays free
until search is actually used. Embeddings are L2-normalized, so cosine
similarity is a single numpy matmul (no scikit-learn).
"""
import html
import math
import os
import pickle
import re
import time
from typing import Any, Callable, Dict, List, Optional

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    NUMPY_AVAILABLE = False
    np = None

from .bm25 import BM25, tokenize
from .fusion import rrf

# ----- optional heavy deps (sentence-transformers / torch / pypdf) ----------

SEARCH_DEPS_AVAILABLE = False
SentenceTransformer = None
CrossEncoder = None
torch = None

BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def _try_import_search_deps() -> bool:
    global SEARCH_DEPS_AVAILABLE, SentenceTransformer, CrossEncoder, torch
    try:
        from sentence_transformers import SentenceTransformer as ST, CrossEncoder as CE
        import torch as t
        SentenceTransformer = ST
        CrossEncoder = CE
        torch = t
        SEARCH_DEPS_AVAILABLE = True
        return True
    except Exception as e:
        print(f"Warning: search dependencies unavailable ({e}). Semantic search disabled.")
        return False


PDF_SUPPORT = False
pypdf = None


def _try_import_pdf() -> bool:
    global PDF_SUPPORT, pypdf
    try:
        import pypdf as p
        pypdf = p
        PDF_SUPPORT = True
        return True
    except ImportError:
        print("Warning: pypdf not available. PDF indexing disabled.")
        return False


# ----------------------------------------------------------------- snippets

def make_snippet(text: str, query: str, window: int = 40) -> str:
    """HTML-safe excerpt around the first query-term hit, terms <mark>-highlighted."""
    words = " ".join(text.split()).split(" ")
    qset = {t for t in tokenize(query) if len(t) >= 2}
    start = 0
    for i, w in enumerate(words):
        toks = tokenize(w)
        if toks and toks[0] in qset:
            start = max(0, i - window // 2)
            break
    snippet = html.escape(" ".join(words[start:start + window]))
    if start > 0:
        snippet = "… " + snippet
    if start + window < len(words):
        snippet = snippet + " …"
    for t in sorted(qset, key=len, reverse=True):
        snippet = re.sub(r"(?i)\b(" + re.escape(t) + r")\b", r"<mark>\1</mark>", snippet)
    return snippet


def extract_text_file(filepath: str, max_file_size_mb: int) -> Optional[str]:
    """Module-level text extraction (used by parallel index builds)."""
    _, ext = os.path.splitext(filepath)
    ext = ext.lower()
    try:
        if os.path.getsize(filepath) > max_file_size_mb * 1024 * 1024:
            return None
    except OSError:
        return None
    try:
        if ext in (".txt", ".md", ".markdown"):
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        if ext == ".pdf":
            try:
                import pypdf
            except ImportError:
                return None
            text = []
            try:
                for page in pypdf.PdfReader(filepath).pages:
                    t = page.extract_text()
                    if t:
                        text.append(t)
            except Exception:
                return None
            return "\n".join(text)
    except Exception:
        return None
    return None


def _extract_worker(args):
    filepath, max_mb = args
    return filepath, extract_text_file(filepath, max_mb)


def cap_chunks(chunks: List[str], cap: int) -> List[str]:
    """Return at most `cap` chunks, sampled evenly across the document."""
    if cap and len(chunks) > cap:
        step = len(chunks) / cap
        return [chunks[int(i * step)] for i in range(cap)]
    return chunks


def _minmax(d: Dict[str, float]) -> Dict[str, float]:
    if not d:
        return {}
    lo, hi = min(d.values()), max(d.values())
    if hi - lo < 1e-9:
        return {k: 0.0 for k in d}
    return {k: (v - lo) / (hi - lo) for k, v in d.items()}


class SearchService:
    """Hybrid + reranked semantic search over indexed file content."""

    def __init__(
        self,
        model_name: str,
        cache_dir: str,
        index_file: str,
        supported_extensions: List[str],
        max_chunk_size: int = 500,
        chunk_overlap: int = 80,
        max_file_size_mb: int = 50,
        max_chunks_per_file: int = 0,
        rerank_model_name: Optional[str] = None,
        top_n: int = 15,
        rerank_candidates: int = 30,
        w_rerank: float = 0.70,
        w_pop: float = 0.15,
        w_traj: float = 0.15,
    ):
        self.model_name = model_name
        self.rerank_model_name = rerank_model_name
        self.cache_dir = cache_dir
        self.index_file = index_file
        self.supported_extensions = supported_extensions
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_file_size_mb = max_file_size_mb
        self.max_chunks_per_file = max_chunks_per_file
        self.top_n = top_n
        self.rerank_candidates = rerank_candidates
        self.w_rerank, self.w_pop, self.w_traj = w_rerank, w_pop, w_traj

        self.model = None        # lazy
        self.reranker = None     # lazy; False once a load attempt failed
        self.index_data: Optional[Dict[str, Any]] = None
        self._bm25: Optional[BM25] = None
        self.deps_ok = False

        os.makedirs(cache_dir, exist_ok=True)
        self.index_file_path = os.path.join(cache_dir, index_file)

        if _try_import_search_deps():
            _try_import_pdf()
            self.deps_ok = True
            self._load_index()

    # ------------------------------------------------------------- status

    @property
    def is_available(self) -> bool:
        """Search dependencies are importable (model loads lazily)."""
        return self.deps_ok

    @property
    def is_index_ready(self) -> bool:
        return (
            self.index_data is not None
            and self.index_data.get("embeddings") is not None
            and self.index_data["embeddings"].shape[0] > 0
        )

    # -------------------------------------------------------- model loading

    def _ensure_model(self) -> bool:
        if self.model is not None:
            return True
        if not self.deps_ok:
            return False
        device = "cuda" if (torch and torch.cuda.is_available()) else "cpu"
        try:
            # Use all CPU cores for embedding/rerank (esp. for index builds).
            if torch and device == "cpu":
                try:
                    torch.set_num_threads(max(1, os.cpu_count() or 1))
                except Exception:
                    pass
            print(f"Loading embedding model {self.model_name} on {device}...")
            self.model = SentenceTransformer(self.model_name, device=device)
            return True
        except Exception as e:
            print(f"Error loading embedding model: {e}")
            return False

    def _ensure_reranker(self) -> bool:
        if self.reranker is not None:
            return bool(self.reranker)
        if not self.deps_ok or not self.rerank_model_name:
            self.reranker = False
            return False
        try:
            print(f"Loading reranker {self.rerank_model_name}...")
            self.reranker = CrossEncoder(self.rerank_model_name)
            return True
        except Exception as e:
            print(f"Warning: reranker unavailable ({e}); skipping rerank.")
            self.reranker = False
            return False

    def encode_texts(self, texts: List[str]) -> "np.ndarray":
        """L2-normalized embeddings for passages/names (used by nav model too)."""
        if not self._ensure_model() or not texts:
            return np.zeros((0, 384), dtype=np.float32)
        return self.model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True,
            batch_size=64, show_progress_bar=False,
        ).astype(np.float32)

    def encode_query(self, query: str) -> Optional["np.ndarray"]:
        if not self._ensure_model():
            return None
        # bge models want a query instruction prefix; MiniLM and others do not.
        if "bge" in self.model_name.lower():
            query = BGE_QUERY_INSTRUCTION + query
        vec = self.model.encode(
            query, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False,
        )
        return np.asarray(vec, dtype=np.float32)

    # ------------------------------------------------------------- indexing

    def _read_index_file(self) -> Optional[Dict[str, Any]]:
        if not os.path.exists(self.index_file_path):
            return None
        try:
            with open(self.index_file_path, "rb") as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Error reading index file: {e}")
            return None

    def _atomic_save(self, data: Dict[str, Any]) -> None:
        """Write the index via a temp file + rename so a crash can't corrupt it."""
        tmp = self.index_file_path + ".tmp"
        with open(tmp, "wb") as f:
            pickle.dump(data, f)
        os.replace(tmp, self.index_file_path)

    def _load_index(self) -> None:
        data = self._read_index_file()
        if data is None:
            print("Semantic index not found. POST /rebuild-index to build.")
            return
        if not self._validate_index(data):
            print("Index invalid or from a different model; rebuild recommended.")
            return
        # A build in progress is usable up to embedded_count.
        ec = int(data.get("embedded_count", data["embeddings"].shape[0]))
        if 0 < ec < data["embeddings"].shape[0]:
            data = {**data, "embeddings": data["embeddings"][:ec], "metadata": data["metadata"][:ec]}
        self.index_data = data
        self._build_bm25()
        state = "complete" if data.get("complete", True) else "partial (building)"
        print(f"Loaded {state} index: {self.index_data['embeddings'].shape[0]} chunks "
              f"from {len(set(m['path'] for m in self.index_data['metadata']))} files.")

    def _validate_index(self, data: Dict) -> bool:
        if not isinstance(data, dict) or data.get("version") != 2:
            return False
        if "embeddings" not in data or "metadata" not in data:
            return False
        if not isinstance(data["embeddings"], np.ndarray):
            return False
        if data.get("model") != self.model_name:
            return False
        return True

    def _build_bm25(self) -> None:
        if not self.index_data:
            self._bm25 = None
            return
        corpus = [tokenize(m.get("text", "")) for m in self.index_data["metadata"]]
        self._bm25 = BM25(corpus)

    def extract_text_from_file(self, filepath: str) -> Optional[str]:
        _, ext = os.path.splitext(filepath)
        ext = ext.lower()
        try:
            if os.path.getsize(filepath) > self.max_file_size_mb * 1024 * 1024:
                return None
        except OSError:
            return None
        try:
            if ext in (".txt", ".md", ".markdown"):
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            if ext == ".pdf" and PDF_SUPPORT:
                text = ""
                try:
                    reader = pypdf.PdfReader(filepath)
                    for page in reader.pages:
                        t = page.extract_text()
                        if t:
                            text += t + "\n"
                except Exception as e:
                    print(f"Warning: could not read PDF {filepath}: {e}")
                    return None
                return text
        except Exception as e:
            print(f"Error extracting {filepath}: {e}")
        return None

    def _chunk_text(self, text: str) -> List[str]:
        words = text.split()
        if not words:
            return []
        stride = max(1, self.max_chunk_size - self.chunk_overlap)
        return [
            " ".join(words[i:i + self.max_chunk_size])
            for i in range(0, len(words), stride)
        ]

    def build_index(self, public_dir: str) -> Optional[Dict[str, Any]]:
        if not self._ensure_model():
            print("Model not loaded; cannot build index.")
            return None
        print("Building semantic index...")
        start = time.time()
        texts: List[str] = []
        metadata: List[Dict[str, Any]] = []

        # Collect eligible files
        file_list = []
        for root, _, files in os.walk(public_dir):
            for filename in files:
                _, ext = os.path.splitext(filename)
                if ext.lower() in self.supported_extensions:
                    file_list.append(os.path.join(root, filename))
        print(f"Extracting text from {len(file_list)} files across CPU cores...")

        # Parallel text extraction (spawn context avoids torch/fork deadlocks)
        import concurrent.futures
        import multiprocessing as _mp
        args = [(p, self.max_file_size_mb) for p in file_list]
        try:
            ctx = _mp.get_context("spawn")
            with concurrent.futures.ProcessPoolExecutor(
                max_workers=max(1, os.cpu_count() or 2), mp_context=ctx
            ) as ex:
                results = list(ex.map(_extract_worker, args, chunksize=4))
        except Exception as e:
            print(f"Parallel extraction failed ({e}); using sequential.")
            results = [_extract_worker(a) for a in args]

        for filepath, content in results:
            if not content:
                continue
            rel_path = os.path.relpath(filepath, public_dir).replace(os.sep, "/")
            chunks = cap_chunks(self._chunk_text(content), self.max_chunks_per_file)
            for i, chunk in enumerate(chunks):
                texts.append(chunk)
                metadata.append({"path": rel_path, "chunk_index": i, "text": chunk})
        print(f"Extracted {len(texts)} chunks from {len(set(m['path'] for m in metadata))} files; embedding...")

        dim = self.model.get_sentence_embedding_dimension()
        total = len(texts)

        if total == 0:
            data = {"version": 2, "model": self.model_name, "dim": dim,
                    "embeddings": np.zeros((0, dim), dtype=np.float32),
                    "metadata": [], "total": 0, "embedded_count": 0, "complete": True}
            self._atomic_save(data)
            self.index_data = data
            self._build_bm25()
            return data

        embeddings = np.zeros((total, dim), dtype=np.float32)
        start_at = 0

        # Resume an interrupted build if the on-disk index matches this corpus.
        prev = self._read_index_file()
        if (prev and prev.get("model") == self.model_name and prev.get("total") == total
                and isinstance(prev.get("embeddings"), np.ndarray)
                and prev["embeddings"].shape == (total, dim)
                and len(prev.get("metadata", [])) == total
                and all(prev["metadata"][k]["path"] == metadata[k]["path"]
                        for k in range(0, total, max(1, total // 50)))):
            embeddings = prev["embeddings"].astype(np.float32)
            start_at = min(int(prev.get("embedded_count", 0)), total)
            if start_at:
                print(f"Resuming embedding from {start_at}/{total}.", flush=True)

        # Embed in batches, checkpointing after each so the long build is
        # crash-resilient and searchable while still in progress.
        BATCH = 2000
        for s in range(start_at, total, BATCH):
            e = min(s + BATCH, total)
            embeddings[s:e] = self.encode_texts(texts[s:e])
            data = {"version": 2, "model": self.model_name, "dim": dim,
                    "embeddings": embeddings, "metadata": metadata,
                    "total": total, "embedded_count": e, "complete": e >= total}
            try:
                self._atomic_save(data)
            except Exception as ex:
                print(f"Error saving checkpoint: {ex}")
            print(f"Embedded {e}/{total} ({100 * e / total:.1f}%) "
                  f"elapsed={int(time.time() - start)}s", flush=True)

        # Finalize (serve only the embedded rows, which is all of them now).
        self.index_data = {"version": 2, "model": self.model_name, "dim": dim,
                           "embeddings": embeddings, "metadata": metadata,
                           "total": total, "embedded_count": total, "complete": True}
        self._build_bm25()
        print(f"Indexed {len(set(m['path'] for m in metadata))} files / "
              f"{total} chunks in {time.time() - start:.1f}s.")
        return self.index_data

    # --------------------------------------------------------------- search

    def _popularity_scores(self, paths, popularity, now) -> Dict[str, float]:
        if not popularity:
            return {p: 0.0 for p in paths}
        raw = {}
        for p in paths:
            info = popularity.get(p)
            if not info:
                raw[p] = 0.0
                continue
            recency = math.exp(-(now - info["last_ts"]) / (14 * 86400)) if info.get("last_ts") else 0.0
            raw[p] = math.log1p(info.get("count", 0)) * (1 + recency)
        return _minmax(raw)

    def search(
        self,
        query: str,
        top_n: Optional[int] = None,
        popularity: Optional[Dict[str, Dict[str, Any]]] = None,
        prior_fn: Optional[Callable[[List[str]], Dict[str, float]]] = None,
        now: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Run the full hybrid+rerank pipeline and return ranked files."""
        if not self.is_index_ready or self._bm25 is None:
            return []
        qvec = self.encode_query(query)
        if qvec is None:
            return []
        top_n = top_n or self.top_n
        now = time.time() if now is None else now

        embeddings = self.index_data["embeddings"]
        metadata = self.index_data["metadata"]

        # 1. semantic + lexical rankings
        sem_scores = embeddings @ qvec
        bm_scores = self._bm25.get_scores(tokenize(query))
        pool = max(self.rerank_candidates * 2, 50)
        sem_rank = list(np.argsort(sem_scores)[::-1][:pool].astype(int))
        bm_rank = list(np.argsort(bm_scores)[::-1][:pool].astype(int))

        # 2. fuse, keep the best candidate chunks
        fused = rrf([sem_rank, bm_rank])
        candidates = [(idx, sc) for idx, sc in fused[: self.rerank_candidates]]
        if not candidates:
            return []

        # 3. rerank (or fall back to fused scores)
        if self._ensure_reranker():
            pairs = [(query, metadata[i]["text"][:1024]) for i, _ in candidates]
            rscores = self.reranker.predict(pairs)
            scored = list(zip([i for i, _ in candidates], [float(s) for s in rscores]))
        else:
            scored = candidates

        # 4. collapse to best chunk per file
        best: Dict[str, Dict[str, Any]] = {}
        for chunk_idx, score in scored:
            path = metadata[chunk_idx]["path"]
            if path not in best or score > best[path]["rerank"]:
                best[path] = {"chunk": int(chunk_idx), "rerank": float(score)}
        paths = list(best.keys())

        # 5. blend rerank + popularity + trajectory prior
        rr_norm = _minmax({p: best[p]["rerank"] for p in paths})
        pop_norm = self._popularity_scores(paths, popularity, now)
        traj = prior_fn(paths) if prior_fn else {}

        results = []
        for p in paths:
            final = (
                self.w_rerank * rr_norm.get(p, 0.0)
                + self.w_pop * pop_norm.get(p, 0.0)
                + self.w_traj * traj.get(p, 0.0)
            )
            results.append({
                "path": p,
                "score": final,
                "snippet": make_snippet(metadata[best[p]["chunk"]]["text"], query),
                "components": {
                    "rerank": rr_norm.get(p, 0.0),
                    "popularity": pop_norm.get(p, 0.0),
                    "trajectory": traj.get(p, 0.0),
                },
            })
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_n]
