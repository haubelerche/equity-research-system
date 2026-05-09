from __future__ import annotations

import argparse
import hashlib
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import pdfplumber
from bs4 import BeautifulSoup

from scripts.dataset.config_io import ROOT, load_universe_tickers
from scripts.db.milvus_store import ChunkRecord, MilvusStore

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency at runtime
    OpenAI = None


RAW_ROOT = ROOT / "dataset" / "raw"
DEFAULT_EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
VECTOR_DIM = 1536


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source_version_id: str
    company_ticker: str
    chunk_type: str
    language: str
    content: str
    content_hash: str
    embedding_model: str
    ingested_at: str


def _source_version_id_for_path(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()


def _detect_ticker(path: Path) -> str:
    tickers = set(load_universe_tickers())
    for part in path.parts:
        token = part.upper()
        if token in tickers:
            return token
    return "UNKNOWN"


def _split_text(text: str, max_chars: int = 1800) -> list[str]:
    blocks = [blk.strip() for blk in re.split(r"\n{2,}", text) if blk.strip()]
    chunks: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}".strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = block[:max_chars]
    if current:
        chunks.append(current)
    return chunks


def _chunk_pdf(path: Path) -> list[tuple[str, str]]:
    pieces: list[tuple[str, str]] = []
    with pdfplumber.open(path) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                for chunk in _split_text(text):
                    chunk_type = "table" if "|" in chunk and len(chunk.splitlines()) > 3 else "section"
                    pieces.append((chunk_type, f"[page {page_idx}]\n{chunk}"))
    return pieces


def _chunk_html(path: Path) -> list[tuple[str, str]]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    chunks: list[tuple[str, str]] = []
    for table in soup.find_all("table"):
        text = table.get_text(" ", strip=True)
        if text:
            chunks.append(("table", text[:2500]))
    body_text = soup.get_text("\n", strip=True)
    for block in _split_text(body_text):
        chunks.append(("regulatory_clause" if "điều" in block.lower() else "section", block))
    return chunks


def _chunk_text(path: Path) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [("note", block) for block in _split_text(text)]


def _iter_documents(root: Path) -> Iterable[Path]:
    for ext in ("*.pdf", "*.html", "*.htm", "*.txt"):
        yield from root.rglob(ext)


def _build_chunks_from_document(path: Path) -> list[Chunk]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        raw_chunks = _chunk_pdf(path)
    elif suffix in {".html", ".htm"}:
        raw_chunks = _chunk_html(path)
    else:
        raw_chunks = _chunk_text(path)

    ticker = _detect_ticker(path)
    source_version_id = _source_version_id_for_path(path)
    now = datetime.now(UTC).isoformat()
    chunks: list[Chunk] = []
    for i, (chunk_type, content) in enumerate(raw_chunks):
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunk_id = hashlib.sha256(f"{path}|{i}|{content_hash}".encode("utf-8")).hexdigest()
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                source_version_id=source_version_id,
                company_ticker=ticker,
                chunk_type=chunk_type,
                language="vi",
                content=content[:8000],
                content_hash=content_hash,
                embedding_model=DEFAULT_EMBED_MODEL,
                ingested_at=now,
            )
        )
    return chunks


def _embed_texts(texts: list[str]) -> list[list[float]]:
    if OpenAI is None or not os.getenv("OPENAI_API_KEY"):
        # deterministic zero vector fallback for local dry runs
        return [[0.0] * VECTOR_DIM for _ in texts]

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = client.embeddings.create(model=DEFAULT_EMBED_MODEL, input=texts)
    return [item.embedding for item in response.data]


def run_chunk_pipeline(root: Path = RAW_ROOT) -> int:
    docs = list(_iter_documents(root))
    if not docs:
        print(f"No documents found under {root}")
        return 0

    milvus = MilvusStore(vector_dim=VECTOR_DIM)
    milvus.ensure_collection()

    total = 0
    for doc in docs:
        chunks = _build_chunks_from_document(doc)
        if not chunks:
            continue
        embeddings = _embed_texts([chunk.content for chunk in chunks])
        records = [
            ChunkRecord(
                chunk_id=chunk.chunk_id,
                source_version_id=chunk.source_version_id,
                company_ticker=chunk.company_ticker,
                chunk_type=chunk.chunk_type,
                language=chunk.language,
                content=chunk.content,
                content_hash=chunk.content_hash,
                embedding_model=chunk.embedding_model,
                ingested_at=chunk.ingested_at,
                embedding=embedding,
            )
            for chunk, embedding in zip(chunks, embeddings, strict=False)
        ]
        milvus.upsert_chunks(records)
        total += len(records)
        print(f"[chunk] {doc}: {len(records)} chunks")
    print(f"Chunk pipeline completed: {total} chunks indexed")
    return total


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Chunk raw docs and index embeddings into Milvus.")
    parser.add_argument("--root", type=str, default=str(RAW_ROOT), help="Root directory to scan for raw documents.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_chunk_pipeline(root=Path(args.root))


if __name__ == "__main__":
    main()

