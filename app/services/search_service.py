"""
Semantic search service using sentence transformers.
"""
import os
import pickle
import time
from typing import Dict, List, Optional, Any

# Core dependencies
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None

# Optional imports - gracefully handle if not available
SEARCH_DEPS_AVAILABLE = False
SentenceTransformer = None
torch = None
cosine_similarity = None

def _try_import_search_deps():
    """Attempt to import search dependencies."""
    global SEARCH_DEPS_AVAILABLE, SentenceTransformer, torch, cosine_similarity
    try:
        from sentence_transformers import SentenceTransformer as ST
        import torch as t
        from sklearn.metrics.pairwise import cosine_similarity as cs
        SentenceTransformer = ST
        torch = t
        cosine_similarity = cs
        SEARCH_DEPS_AVAILABLE = True
        return True
    except ImportError as e:
        print(f"Warning: Search dependencies not available ({e}). Semantic search disabled.")
        return False
    except Exception as e:
        print(f"Warning: Error loading search dependencies ({e}). Semantic search disabled.")
        return False

# Try to import on module load (deferred to avoid import-time errors)
# We'll try again in SearchService.__init__ if needed

# PDF support
PDF_SUPPORT = False
pypdf = None

def _try_import_pdf():
    """Attempt to import PDF support."""
    global PDF_SUPPORT, pypdf
    try:
        import pypdf as p
        pypdf = p
        PDF_SUPPORT = True
        return True
    except ImportError:
        print("Warning: pypdf not available. PDF indexing disabled.")
        return False


class SearchService:
    """Handles semantic search functionality."""
    
    def __init__(
        self, 
        model_name: str,
        cache_dir: str,
        index_file: str,
        supported_extensions: List[str],
        max_chunk_size: int = 500,
        max_file_size_mb: int = 50
    ):
        """
        Initialize the search service.
        
        Args:
            model_name: Name of the sentence transformer model
            cache_dir: Directory for caching
            index_file: Name of the index file
            supported_extensions: List of supported file extensions
            max_chunk_size: Maximum words per chunk
            max_file_size_mb: Maximum file size to process in MB
        """
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.index_file = index_file
        self.supported_extensions = supported_extensions
        self.max_chunk_size = max_chunk_size
        self.max_file_size_mb = max_file_size_mb
        
        self.model = None
        self.index_data: Optional[Dict[str, Any]] = None
        self.model_loaded = False
        
        # Ensure cache directory exists
        os.makedirs(cache_dir, exist_ok=True)
        self.index_file_path = os.path.join(cache_dir, index_file)
        
        # Try to import dependencies and load model
        if _try_import_search_deps():
            _try_import_pdf()
            self._load_model()
            self._load_index()
    
    @property
    def is_available(self) -> bool:
        """Check if search functionality is available."""
        return self.model_loaded
    
    @property
    def is_index_ready(self) -> bool:
        """Check if the index is loaded and ready."""
        return self.index_data is not None and self.index_data.get("embeddings") is not None
    
    def _load_model(self) -> None:
        """Load the sentence transformer model."""
        if not SEARCH_DEPS_AVAILABLE:
            return
        
        print(f"Loading sentence transformer model: {self.model_name}...")
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.model = SentenceTransformer(self.model_name, device=device)
            self.model_loaded = True
            print(f"Model loaded successfully on device: {device}")
        except Exception as e:
            print(f"Error loading Sentence Transformer model: {e}")
            self.model_loaded = False
    
    def _load_index(self) -> None:
        """Load the semantic index from file."""
        if not self.model_loaded:
            return
        
        if os.path.exists(self.index_file_path):
            try:
                with open(self.index_file_path, "rb") as f:
                    print(f"Loading semantic index from {self.index_file_path}...")
                    index_data = pickle.load(f)
                    
                    if self._validate_index(index_data):
                        self.index_data = index_data
                        print(f"Loaded index with {index_data['embeddings'].shape[0]} embeddings.")
                    else:
                        print("Invalid index file. Rebuilding recommended.")
            except Exception as e:
                print(f"Error loading index file: {e}")
        else:
            print("Semantic index file not found.")
    
    def _validate_index(self, index_data: Dict) -> bool:
        """Validate index data structure and dimensions."""
        if not isinstance(index_data, dict):
            return False
        if "embeddings" not in index_data or "metadata" not in index_data:
            return False
        if not isinstance(index_data["embeddings"], np.ndarray):
            return False
        
        # Check embedding dimensions match model
        if (index_data["embeddings"].shape[0] > 0 and 
            index_data["embeddings"].shape[1] != self.model.get_sentence_embedding_dimension()):
            print("Warning: Index embedding dimensions don't match model.")
            return False
        
        return True
    
    def extract_text_from_file(self, filepath: str) -> Optional[str]:
        """
        Extract text content from supported file types.
        
        Args:
            filepath: Path to the file
            
        Returns:
            Extracted text or None
        """
        _, ext = os.path.splitext(filepath)
        ext = ext.lower()
        
        # Check file size
        try:
            if os.path.getsize(filepath) > self.max_file_size_mb * 1024 * 1024:
                print(f"Skipping large file (>{self.max_file_size_mb}MB): {filepath}")
                return None
        except OSError:
            return None
        
        try:
            if ext == ".txt":
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            elif ext == ".pdf" and PDF_SUPPORT and pypdf is not None:
                text = ""
                try:
                    reader = pypdf.PdfReader(filepath)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                except Exception as e:
                    print(f"Warning: Could not read PDF {filepath}: {e}")
                    return None
                return text
            else:
                return None
        except Exception as e:
            print(f"Error extracting text from {filepath}: {e}")
            return None
    
    def _chunk_text(self, text: str) -> List[str]:
        """Split text into chunks of max_chunk_size words."""
        words = text.split()
        chunks = []
        current_chunk = []
        word_count = 0
        
        for word in words:
            current_chunk.append(word)
            word_count += 1
            if word_count >= self.max_chunk_size:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                word_count = 0
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks
    
    def build_index(self, public_dir: str) -> Optional[Dict[str, Any]]:
        """
        Build the semantic search index.
        
        Args:
            public_dir: The public directory to index
            
        Returns:
            Index data or None on failure
        """
        if not self.model_loaded:
            print("Model not loaded. Cannot build index.")
            return None
        
        print("Starting semantic index build...")
        start_time = time.time()
        
        index_data = {"embeddings": [], "metadata": []}
        files_processed = 0
        chunks_processed = 0
        
        for root, _, files in os.walk(public_dir):
            for filename in files:
                _, ext = os.path.splitext(filename)
                if ext.lower() not in self.supported_extensions:
                    continue
                
                abs_path = os.path.join(root, filename)
                if not abs_path.startswith(public_dir):
                    continue
                
                rel_path = os.path.relpath(abs_path, public_dir)
                print(f"  Processing: {rel_path}")
                files_processed += 1
                
                text = self.extract_text_from_file(abs_path)
                if not text:
                    continue
                
                chunks = self._chunk_text(text)
                if not chunks:
                    continue
                
                try:
                    chunk_embeddings = self.model.encode(
                        chunks, 
                        convert_to_tensor=True, 
                        show_progress_bar=False
                    )
                    
                    index_data["embeddings"].append(chunk_embeddings.cpu().numpy())
                    for i in range(len(chunks)):
                        index_data["metadata"].append({
                            "path": rel_path, 
                            "chunk_index": i
                        })
                        chunks_processed += 1
                except Exception as e:
                    print(f"Error encoding chunks for {rel_path}: {e}")
        
        # Finalize index
        if not index_data["embeddings"]:
            print("No embeddings generated. Index is empty.")
            if np is not None:
                index_data["embeddings"] = np.array([]).reshape(
                    0, self.model.get_sentence_embedding_dimension()
                )
            else:
                index_data["embeddings"] = []
        else:
            if np is not None:
                index_data["embeddings"] = np.concatenate(index_data["embeddings"], axis=0)
        
        # Save index
        try:
            with open(self.index_file_path, "wb") as f:
                pickle.dump(index_data, f)
            
            end_time = time.time()
            print(f"Semantic index built and saved to {self.index_file_path}")
            print(f"Processed {files_processed} files, {chunks_processed} text chunks.")
            print(f"Index build took {end_time - start_time:.2f} seconds.")
            
            self.index_data = index_data
            return index_data
        except Exception as e:
            print(f"Error saving index file: {e}")
            return None
    
    def search(self, query: str, top_n: int = 15) -> List[Dict[str, Any]]:
        """
        Perform semantic search.
        
        Args:
            query: Search query
            top_n: Number of results to return
            
        Returns:
            List of search results with path and score
        """
        if not self.model_loaded:
            print("Model not loaded. Cannot search.")
            return []
        
        if not self.is_index_ready or self.index_data["embeddings"].shape[0] == 0:
            print("Index not ready. Cannot search.")
            return []
        
        try:
            query_embedding = self.model.encode(query, convert_to_tensor=True)
            query_embedding_np = query_embedding.cpu().numpy().reshape(1, -1)
            
            sims = cosine_similarity(query_embedding_np, self.index_data["embeddings"])[0]
            top_indices = np.argsort(sims)[::-1][:top_n]
            
            results = []
            seen_paths = set()
            
            for idx in top_indices:
                score = float(sims[idx])
                if score < 0.05:  # Relevance threshold
                    continue
                
                metadata = self.index_data["metadata"][idx]
                rel_path = metadata["path"]
                
                if rel_path not in seen_paths:
                    results.append({"path": rel_path, "score": score})
                    seen_paths.add(rel_path)
            
            results.sort(key=lambda x: x["score"], reverse=True)
            return results
            
        except Exception as e:
            print(f"Error during semantic search for '{query}': {e}")
            return []

