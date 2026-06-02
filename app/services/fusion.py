"""
Reciprocal Rank Fusion (RRF) for combining ranked candidate lists.

RRF is robust and parameter-light: an item ranked highly in several lists beats
an item ranked highly in only one, without needing the source scores to be on
comparable scales.
"""
from typing import List, Tuple


def rrf(rankings: List[List[int]], k: int = 60) -> List[Tuple[int, float]]:
    """
    Fuse several rankings (each a list of item ids, best first).

    Returns (item_id, fused_score) pairs sorted by score descending.
    """
    scores: dict = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
