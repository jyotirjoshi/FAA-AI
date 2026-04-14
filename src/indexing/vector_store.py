import json
import os
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from src.config import settings
from src.models import Chunk, RetrievedChunk


class LocalVectorStore:
    def __init__(self, index_dir: Path):
        self.index_dir = index_dir
        self.index_dir.mkdir(parents=True, exist_ok=True)
        # Pass HF_TOKEN so authenticated downloads work on HF Spaces
        # (avoids 429 rate-limit on the builder/runtime IP).
        hf_token = os.environ.get("HF_TOKEN") or None
        self.embedding_model = SentenceTransformer(settings.embedding_model, token=hf_token)

        self.emb_path = self.index_dir / "embeddings.npy"
        self.meta_path = self.index_dir / "chunks.jsonl"

        self.embeddings: np.ndarray | None = None
        self.chunks: list[Chunk] = []

    def build(self, chunks: list[Chunk]) -> None:
        texts = [c.text for c in chunks]
        embeddings = self.embedding_model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
        self.embeddings = np.asarray(embeddings, dtype=np.float32)
        self.chunks = chunks
        np.save(self.emb_path, self.embeddings)

        with self.meta_path.open("w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c.__dict__, ensure_ascii=False) + "\n")

    def load(self) -> None:
        self.embeddings = np.load(self.emb_path)
        self.chunks = []
        with self.meta_path.open("r", encoding="utf-8") as f:
            for line in f:
                payload = json.loads(line)
                self.chunks.append(Chunk(**payload))

    def search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        if self.embeddings is None:
            raise RuntimeError("Index not loaded")
        query_emb = self.embedding_model.encode([query], normalize_embeddings=True)
        query_emb = np.asarray(query_emb[0], dtype=np.float32)

        sims = self.embeddings @ query_emb
        idxs = np.argsort(-sims)[:top_k]

        return [RetrievedChunk(chunk=self.chunks[i], score=float(sims[i])) for i in idxs]
