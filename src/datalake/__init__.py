"""KMFlow Data Lake module.

Provides a storage abstraction layer (StorageBackend protocol) with
implementations for local filesystem, Delta Lake (via delta-rs), and
a future Databricks backend. Enables medallion architecture (Bronze /
Silver / Gold) without coupling the evidence pipeline to a specific
storage technology.

Submodules:
- ``backend``: StorageBackend protocol + implementations (Phase B)
- ``silver``: Silver layer writers for fragments, entities, quality (Phase C)
- ``lineage``: Evidence lineage tracking service (Phase C)
"""

from src.datalake.backend import (
    DeltaLakeBackend,
    LocalFilesystemBackend,
    StorageBackend,
    get_storage_backend,
)
from src.datalake.lineage import (
    append_transformation,
    create_lineage_record,
    get_lineage_chain,
)
from src.datalake.silver import SilverLayerWriter

__all__ = [
    "DeltaLakeBackend",
    "LocalFilesystemBackend",
    "SilverLayerWriter",
    "StorageBackend",
    "append_transformation",
    "create_lineage_record",
    "get_lineage_chain",
    "get_storage_backend",
]
