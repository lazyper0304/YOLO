"""RAG knowledge base configuration."""

import os
from pathlib import Path


class RAGSettings:
    """RAG-related configuration."""

    # ChromaDB persistent storage directory
    RAG_CHROMA_DIR: str = os.getenv(
        "RAG_CHROMA_DIR",
        str(Path(__file__).resolve().parent.parent.parent / "chroma_data"),
    )

    # Sentence-transformers embedding model
    RAG_EMBEDDING_MODEL: str = os.getenv(
        "RAG_EMBEDDING_MODEL",
        "paraphrase-multilingual-MiniLM-L12-v2",
    )

    # Chunking parameters
    RAG_CHUNK_SIZE: int = int(os.getenv("RAG_CHUNK_SIZE", "512"))
    RAG_CHUNK_OVERLAP: int = int(os.getenv("RAG_CHUNK_OVERLAP", "64"))

    # Retrieval parameters
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "5"))
    RAG_MAX_CONTEXT_TOKENS: int = int(os.getenv("RAG_MAX_CONTEXT_TOKENS", "2000"))

    # Document storage directory
    RAG_DOC_DIR: str = os.getenv(
        "RAG_DOC_DIR",
        str(Path(__file__).resolve().parent.parent.parent / "uploads" / "documents"),
    )

    # Max document file size in MB
    RAG_MAX_FILE_SIZE_MB: int = int(os.getenv("RAG_MAX_FILE_SIZE_MB", "50"))

    # Max image file size in MB
    RAG_IMAGE_MAX_SIZE_MB: int = int(os.getenv("RAG_IMAGE_MAX_SIZE_MB", "10"))

    # Frontend document status poll interval in seconds
    RAG_DOC_POLL_INTERVAL: int = int(os.getenv("RAG_DOC_POLL_INTERVAL", "3"))

    # Embedding API call timeout in seconds
    EMBEDDING_TIMEOUT_SECONDS: int = int(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "120"))
