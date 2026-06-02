"""
Compact BM25 keyword ranking (no external dependency).

Used as the lexical half of hybrid search. Builds a small inverted index so
scoring only touches documents that contain a query term.
"""
import math
import re
from collections import Counter
from typing import List

import numpy as np

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> List[str]:
    """Lowercase word/number tokenization."""
    return _TOKEN_RE.findall(text.lower())


class BM25:
    """Okapi BM25 over a fixed corpus of pre-tokenized documents."""

    def __init__(self, corpus_tokens: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.n = len(corpus_tokens)
        self.doc_len = np.array([len(d) for d in corpus_tokens], dtype=np.float32)
        self.avgdl = float(self.doc_len.mean()) if self.n else 0.0

        # Inverted index: term -> list of (doc_idx, term_freq)
        self.postings: dict = {}
        df = Counter()
        for i, doc in enumerate(corpus_tokens):
            counts = Counter(doc)
            for term, freq in counts.items():
                self.postings.setdefault(term, []).append((i, freq))
                df[term] += 1

        # BM25 idf (always positive thanks to the +1 inside the log)
        self.idf = {
            term: math.log(1 + (self.n - d + 0.5) / (d + 0.5))
            for term, d in df.items()
        }

    def get_scores(self, query_tokens: List[str]) -> np.ndarray:
        """Return a BM25 score per document for the query."""
        scores = np.zeros(self.n, dtype=np.float32)
        if self.avgdl == 0:
            return scores
        for term in set(query_tokens):
            idf = self.idf.get(term)
            if idf is None:
                continue
            for doc_idx, freq in self.postings[term]:
                denom = freq + self.k1 * (
                    1 - self.b + self.b * self.doc_len[doc_idx] / self.avgdl
                )
                scores[doc_idx] += idf * (freq * (self.k1 + 1)) / denom
        return scores
