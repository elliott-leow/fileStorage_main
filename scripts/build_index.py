#!/usr/bin/env python3
"""
Build the semantic search index.

    python scripts/build_index.py            # index the configured PUBLIC_DIR
    python scripts/build_index.py <dir>      # index a specific directory

Must be run as a script (the parallel extractor uses 'spawn', which re-imports
the entry module — guarded by __main__ below).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from app import create_app

    app = create_app()
    ss = app.search_service
    args = [a for a in sys.argv[1:] if a != "--update"]
    incremental = "--update" in sys.argv
    target = args[0] if args else app.config_obj.PUBLIC_DIR
    print(f"model={ss.model_name}  target={target}  mode={'update' if incremental else 'full'}", flush=True)

    t = time.time()
    data = ss.update_index(target) if incremental else ss.build_index(target)
    if data is not None:
        n_files = len(set(m["path"] for m in data["metadata"]))
        print(
            f"INDEX_DONE chunks={data['embeddings'].shape} files={n_files} "
            f"secs={round(time.time() - t, 1)}",
            flush=True,
        )
    else:
        print("INDEX_FAILED", flush=True)


if __name__ == "__main__":
    main()
