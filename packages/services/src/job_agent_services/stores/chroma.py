"""ChromaDB vector store - implements the VectorStore interface."""

import asyncio
import logging
from pathlib import Path
from typing import Any

from job_agent_contracts.interfaces import VectorStore

logger = logging.getLogger(__name__)


class ChromaRAGStore(VectorStore):
    """ChromaDB-backed vector store for RAG retrieval."""

    BATCH_SIZE = 64

    def __init__(self, persist_dir: str = "data/vectordb", collection_name: str = "job_agent"):
        import chromadb

        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._persist_dir = persist_dir
        logger.info("RAG store initialized at %s", persist_dir)

    async def add(self, doc_id: str, text: str, metadata: dict | None = None) -> None:
        """Add a document to the vector store."""
        await asyncio.to_thread(
            self._collection.upsert,
            ids=[doc_id],
            documents=[text],
            metadatas=[metadata] if metadata else None,
        )

    async def add_batch(self, ids: list[str], texts: list[str],
                        metadatas: list[dict] | None = None) -> None:
        """Add multiple documents in batches."""
        for i in range(0, len(ids), self.BATCH_SIZE):
            batch_ids = ids[i:i + self.BATCH_SIZE]
            batch_texts = texts[i:i + self.BATCH_SIZE]
            batch_meta = metadatas[i:i + self.BATCH_SIZE] if metadatas else None
            await asyncio.to_thread(
                self._collection.upsert,
                ids=batch_ids,
                documents=batch_texts,
                metadatas=batch_meta,
            )

    async def query(self, text: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Query similar documents."""
        results = await asyncio.to_thread(
            self._collection.query,
            query_texts=[text],
            n_results=top_k,
        )

        documents = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                documents.append({
                    "doc_id": results["ids"][0][i] if results["ids"] else "",
                    "content": doc,
                    "score": 1 - (results["distances"][0][i] if results["distances"] else 0),
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                })
        return documents

    async def delete(self, doc_id: str) -> None:
        """Remove a document from the store."""
        await asyncio.to_thread(self._collection.delete, ids=[doc_id])
