from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    MilvusClient,
    connections,
)


DEFAULT_COLLECTION = "document_chunks"
DEFAULT_DIMENSION = 1536


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    source_version_id: str
    company_ticker: str
    chunk_type: str
    language: str
    content: str
    content_hash: str
    embedding_model: str
    ingested_at: str
    embedding: list[float]


def default_collection_schema(vector_dim: int = DEFAULT_DIMENSION) -> CollectionSchema:
    fields = [
        FieldSchema("chunk_id", DataType.VARCHAR, max_length=64, is_primary=True),
        FieldSchema("source_version_id", DataType.VARCHAR, max_length=64),
        FieldSchema("company_ticker", DataType.VARCHAR, max_length=10),
        FieldSchema("chunk_type", DataType.VARCHAR, max_length=30),
        FieldSchema("language", DataType.VARCHAR, max_length=5),
        FieldSchema("content", DataType.VARCHAR, max_length=8192),
        FieldSchema("content_hash", DataType.VARCHAR, max_length=64),
        FieldSchema("embedding_model", DataType.VARCHAR, max_length=80),
        FieldSchema("ingested_at", DataType.VARCHAR, max_length=40),
        FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=vector_dim),
    ]
    return CollectionSchema(fields=fields, description="VN pharma retrieval document chunks")


class MilvusStore:
    """Milvus wrapper with deterministic schema for chunk retrieval."""

    def __init__(
        self,
        uri: str | None = None,
        token: str | None = None,
        collection_name: str = DEFAULT_COLLECTION,
        vector_dim: int = DEFAULT_DIMENSION,
    ) -> None:
        self.uri = uri or os.getenv("MILVUS_URI", "http://localhost:19530")
        self.token = token or os.getenv("MILVUS_TOKEN")
        self.collection_name = collection_name
        self.vector_dim = vector_dim

        # MilvusClient is convenient for lifecycle checks.
        self.client = MilvusClient(uri=self.uri, token=self.token)
        connections.connect(alias="default", uri=self.uri, token=self.token)

    def ensure_collection(self) -> None:
        if self.client.has_collection(self.collection_name):
            return

        schema = default_collection_schema(vector_dim=self.vector_dim)
        collection = Collection(name=self.collection_name, schema=schema)
        collection.create_index(
            field_name="embedding",
            index_params={"index_type": "HNSW", "metric_type": "COSINE", "params": {"M": 16, "efConstruction": 200}},
        )
        collection.load()

    def upsert_chunks(self, chunks: Iterable[ChunkRecord]) -> None:
        data = [chunk.__dict__ for chunk in chunks]
        if not data:
            return
        self.client.upsert(collection_name=self.collection_name, data=data)

    def search(
        self,
        embedding: list[float],
        top_k: int = 8,
        filter_expr: str | None = None,
        output_fields: list[str] | None = None,
    ) -> list[dict]:
        fields = output_fields or [
            "chunk_id",
            "source_version_id",
            "company_ticker",
            "chunk_type",
            "language",
            "content",
            "content_hash",
            "embedding_model",
            "ingested_at",
        ]
        return self.client.search(
            collection_name=self.collection_name,
            data=[embedding],
            limit=top_k,
            filter=filter_expr,
            output_fields=fields,
        )

