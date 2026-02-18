"""KMFlow Data Lake module.

Provides a storage abstraction layer (StorageBackend protocol) with
implementations for local filesystem, Delta Lake (via delta-rs), and
a future Databricks backend. Enables medallion architecture (Bronze /
Silver / Gold) without coupling the evidence pipeline to a specific
storage technology.
"""

from src.datalake.backend import (
    DeltaLakeBackend,
    LocalFilesystemBackend,
    StorageBackend,
    get_storage_backend,
)

__all__ = [
    "DeltaLakeBackend",
    "LocalFilesystemBackend",
    "StorageBackend",
    "get_storage_backend",
]
