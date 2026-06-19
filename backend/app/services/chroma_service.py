"""ChromaDB vector store service — singleton with persistent storage."""

import threading
from typing import Any

import chromadb

from app.config import settings


class ChromaService:
    """Singleton ChromaDB service. Each knowledge base gets its own collection."""

    _instance: "ChromaService | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "ChromaService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._client = chromadb.PersistentClient(path=settings.RAG_CHROMA_DIR)

    def get_or_create_collection(self, kb_id: int) -> Any:
        """Get or create a ChromaDB collection for a knowledge base."""
        return self._client.get_or_create_collection(
            name=f"kb_{kb_id}",
            metadata={"hnsw:space": "cosine"},
        )

    def add_chunks(
        self,
        kb_id: int,
        chunk_ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict] | None = None,
    ) -> None:
        """Add document chunks to a knowledge base collection."""
        collection = self.get_or_create_collection(kb_id)
        collection.upsert(
            ids=chunk_ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def query(
        self,
        kb_id: int,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict]:
        """Query the collection for similar chunks."""
        collection = self.get_or_create_collection(kb_id)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "distances", "metadatas"],
        )
        chunks = []
        if results and results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                chunks.append({
                    "id": chunk_id,
                    "content": results["documents"][0][i],
                    "distance": results["distances"][0][i],
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                })
        return chunks

    def delete_chunks(self, kb_id: int, chunk_ids: list[str]) -> None:
        """Delete specific chunks from a collection."""
        if not chunk_ids:
            return
        collection = self.get_or_create_collection(kb_id)
        collection.delete(ids=chunk_ids)

    def delete_collection(self, kb_id: int) -> None:
        """Delete an entire collection for a knowledge base."""
        try:
            self._client.delete_collection(name=f"kb_{kb_id}")
        except Exception:
            pass  # Collection may not exist
