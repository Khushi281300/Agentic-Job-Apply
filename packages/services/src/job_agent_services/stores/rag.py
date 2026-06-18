"""RAG service - high-level retrieval augmented generation operations.

Combines VectorStore + LLM for context-enriched generation.
"""

import logging
import re
from typing import Any

from job_agent_contracts.interfaces import LLMProvider, VectorStore

logger = logging.getLogger(__name__)

# ─── Chunking ────────────────────────────────────────────────────────────────

DEFAULT_CHUNK_SIZE = 400
DEFAULT_CHUNK_OVERLAP = 80


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE,
               overlap: int = DEFAULT_CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks by sentence boundaries."""
    if not text or not text.strip():
        return []

    char_limit = chunk_size * 4
    char_overlap = overlap * 4

    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for sentence in sentences:
        sent_len = len(sentence)

        if sent_len > char_limit:
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_len = 0
            for i in range(0, sent_len, char_limit - char_overlap):
                chunks.append(sentence[i:i + char_limit])
            continue

        if current_len + sent_len > char_limit and current_chunk:
            chunks.append(" ".join(current_chunk))
            overlap_chunk: list[str] = []
            overlap_len = 0
            for s in reversed(current_chunk):
                if overlap_len + len(s) > char_overlap:
                    break
                overlap_chunk.insert(0, s)
                overlap_len += len(s)
            current_chunk = overlap_chunk
            current_len = overlap_len

        current_chunk.append(sentence)
        current_len += sent_len

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


class RAGService:
    """High-level RAG operations combining vector store + LLM."""

    RELEVANCE_THRESHOLD = 0.4

    def __init__(self, llm: LLMProvider, store: VectorStore):
        self.llm = llm
        self.store = store

    async def index_job(self, job_id: str, title: str, company: str, description: str) -> None:
        """Index a job description with semantic chunking."""
        full_text = f"Job: {title} at {company}\n\n{description}"
        chunks = chunk_text(full_text)

        if not chunks:
            return

        if len(chunks) == 1:
            await self.store.add(
                doc_id=f"job_{job_id}",
                text=chunks[0],
                metadata={"type": "job_description", "company": company, "title": title,
                          "chunk": 0, "total_chunks": 1},
            )
            return

        ids = [f"job_{job_id}_c{i}" for i in range(len(chunks))]
        metadatas = [
            {"type": "job_description", "company": company, "title": title,
             "chunk": i, "total_chunks": len(chunks), "parent_id": f"job_{job_id}"}
            for i in range(len(chunks))
        ]

        if hasattr(self.store, "add_batch"):
            await self.store.add_batch(ids=ids, texts=chunks, metadatas=metadatas)
        else:
            for doc_id, text, meta in zip(ids, chunks, metadatas):
                await self.store.add(doc_id=doc_id, text=text, metadata=meta)

    async def index_application(self, job_id: str, company: str, outcome: str, notes: str) -> None:
        """Index application outcome for learning."""
        text = f"Applied to {company}. Outcome: {outcome}. Notes: {notes}"
        await self.store.add(
            doc_id=f"app_{job_id}",
            text=text,
            metadata={"type": "application_history", "outcome": outcome},
        )

    async def index_profile(self, profile_text: str) -> None:
        """Index user profile for matching context."""
        await self.store.add(
            doc_id="user_profile",
            text=profile_text,
            metadata={"type": "profile"},
        )

    async def get_relevant_context(self, query: str, top_k: int = 5) -> str:
        """Retrieve relevant context for a query."""
        results = await self.store.query(query, top_k=top_k)
        if not results:
            return ""

        context_parts = []
        for r in results:
            if r["score"] > self.RELEVANCE_THRESHOLD:
                context_parts.append(f"[{r['metadata'].get('type', 'unknown')}] {r['content'][:500]}")

        return "\n---\n".join(context_parts)

    async def generate_with_context(self, prompt: str, system: str = "",
                                     context_query: str = "") -> str:
        """Generate LLM response augmented with retrieved context."""
        context = ""
        if context_query:
            context = await self.get_relevant_context(context_query)

        augmented_prompt = prompt
        if context:
            augmented_prompt = (
                f"## Relevant Context (from past applications and profile):\n{context}\n\n"
                f"## Current Task:\n{prompt}"
            )

        return await self.llm.generate(augmented_prompt, system=system)

    async def get_similar_jobs(self, job_description: str, top_k: int = 3) -> list[dict]:
        """Find similar jobs from history."""
        results = await self.store.query(job_description, top_k=top_k)
        return [r for r in results if r["metadata"].get("type") == "job_description"]

    async def index_document(self, content: str, metadata: dict | None = None,
                             doc_id: str = "") -> None:
        """Index an arbitrary document."""
        if not doc_id:
            import hashlib
            doc_id = hashlib.sha256(content.encode()).hexdigest()[:16]
        await self.store.add(doc_id=doc_id, text=content, metadata=metadata)
