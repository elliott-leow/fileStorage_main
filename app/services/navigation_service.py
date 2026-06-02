"""
Trajectory-aware navigation model: estimate P(file | browsing path).

Two blended signals rank candidate files by how likely they are the user's
target given the folders visited so far this session:

1. Historical co-occurrence — learned from the user's own past sessions:
   "sessions that passed through folder F usually opened a file in folder G".
   Backtracking (returning to an ancestor) down-weights the abandoned branch.

2. Natural-language prior — semantic, works cold-start: a recency-weighted
   embedding of the visited folders' *names* is compared to each candidate
   folder's name. Visiting "mcat" raises "study" because the names embed close.

The encoder is injected (a callable returning L2-normalized rows) so the math is
unit-testable without loading a model.
"""
import re
from collections import defaultdict
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

from .analytics_service import folder_of

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_LETTER_DIGIT = re.compile(r"(?<=[A-Za-z])(?=[0-9])")
_DIGIT_LETTER = re.compile(r"(?<=[0-9])(?=[A-Za-z])")

RECENCY_DECAY = 0.7
BACKTRACK_PENALTY = 0.3


def normalize_name(s: str) -> str:
    """Turn a folder/file name into space-separated words for embedding.

    'BME221_BIOCHEM' -> 'bme 221 biochem'; 'studyNotes' -> 'study notes'.
    """
    if not s:
        return ""
    s = s.replace("_", " ").replace("-", " ").replace(".", " ").replace("/", " ")
    s = _CAMEL.sub(" ", s)
    s = _LETTER_DIGIT.sub(" ", s)
    s = _DIGIT_LETTER.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1] if path else ""


def _is_ancestor(anc: str, desc: str) -> bool:
    """True if `anc` is a strict ancestor folder of `desc`."""
    if anc == desc:
        return False
    if anc == "":
        return desc != ""
    return desc.startswith(anc + "/")


def _minmax(values: Dict[str, float]) -> Dict[str, float]:
    """Scale a dict of scores into [0, 1]; all-equal -> all zeros (no signal)."""
    if not values:
        return {}
    lo = min(values.values())
    hi = max(values.values())
    if hi - lo < 1e-9:
        return {k: 0.0 for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


class NavigationService:
    """Computes P(file | path) priors from history + folder-name semantics."""

    def __init__(self, analytics_service, encode_fn: Optional[Callable[[List[str]], np.ndarray]] = None):
        self.analytics = analytics_service
        self.encode_fn = encode_fn
        self._name_cache: Dict[str, Optional[np.ndarray]] = {}

    # ----------------------------------------------------------- embeddings

    def embed_name(self, name: str) -> Optional[np.ndarray]:
        """L2-normalized embedding of a normalized name (cached). None if no encoder."""
        norm = normalize_name(name)
        if not norm or self.encode_fn is None:
            return None
        if norm not in self._name_cache:
            try:
                vec = np.asarray(self.encode_fn([norm])[0], dtype=np.float32)
                n = np.linalg.norm(vec)
                self._name_cache[norm] = vec / n if n > 0 else None
            except Exception:
                self._name_cache[norm] = None
        return self._name_cache[norm]

    # ---------------------------------------------------------- trajectory

    @staticmethod
    def _traj_paths(trajectory: Sequence) -> List[str]:
        out = []
        for item in trajectory or []:
            p = item.get("path") if isinstance(item, dict) else item
            if p is not None:
                out.append(p)
        return out

    def _trajectory_weights(self, paths: List[str]) -> List[float]:
        """Recency-decayed weights, with abandoned (backed-out) folders penalized."""
        n = len(paths)
        weights = [RECENCY_DECAY ** (n - 1 - i) for i in range(n)]
        for i, p in enumerate(paths):
            for j in range(i):
                if _is_ancestor(p, paths[j]):  # returned to an ancestor of paths[j]
                    weights[j] *= BACKTRACK_PENALTY
        return weights

    def context_embedding(self, trajectory: Sequence) -> Optional[np.ndarray]:
        """Recency/backtrack-weighted mean of visited folder-name embeddings."""
        paths = self._traj_paths(trajectory)
        if not paths or self.encode_fn is None:
            return None
        weights = self._trajectory_weights(paths)
        acc = None
        for w, p in zip(weights, paths):
            emb = self.embed_name(_basename(p))
            if emb is None:
                continue
            acc = w * emb if acc is None else acc + w * emb
        if acc is None:
            return None
        norm = np.linalg.norm(acc)
        return acc / norm if norm > 0 else None

    # ------------------------------------------------------------ history

    def historical_scores(self, trajectory: Sequence, outcomes=None) -> Dict[str, float]:
        """{target_folder: weight} from past sessions that shared visited folders."""
        if outcomes is None:
            outcomes = self.analytics.session_outcomes() if self.analytics else []
        co: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for o in outcomes:
            target = o.get("target_folder")
            if not target:
                continue
            for v in set(o.get("visited", [])):
                co[v][target] += 1.0
        visited = set(self._traj_paths(trajectory))
        scores: Dict[str, float] = defaultdict(float)
        for v in visited:
            for target, c in co.get(v, {}).items():
                scores[target] += c
        return dict(scores)

    # ------------------------------------------------------------- priors

    def file_priors(self, trajectory: Sequence, candidate_paths: List[str]) -> Dict[str, float]:
        """{path: prior in [0,1]} blending history and folder-name semantics."""
        if not candidate_paths:
            return {}
        outcomes = self.analytics.session_outcomes() if self.analytics else []
        n_outcomes = sum(1 for o in outcomes if o.get("target_folder"))
        alpha = min(0.7, n_outcomes / 10.0)  # trust history more as it accumulates

        ctx = self.context_embedding(trajectory)
        hist = self.historical_scores(trajectory, outcomes=outcomes)

        nl_raw: Dict[str, float] = {}
        hist_raw: Dict[str, float] = {}
        for path in candidate_paths:
            folder = folder_of(path)
            if ctx is not None:
                emb = self.embed_name(_basename(folder))
                nl_raw[path] = float(np.dot(ctx, emb)) if emb is not None else 0.0
            else:
                nl_raw[path] = 0.0
            hist_raw[path] = hist.get(folder, 0.0)

        nl_norm = _minmax(nl_raw)
        hist_norm = _minmax(hist_raw)
        return {
            path: alpha * hist_norm.get(path, 0.0) + (1 - alpha) * nl_norm.get(path, 0.0)
            for path in candidate_paths
        }
