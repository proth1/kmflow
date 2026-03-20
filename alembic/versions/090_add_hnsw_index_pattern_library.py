"""090: Add HNSW index on pattern_library_entries.embedding for fast cosine similarity search.

Using pgvector's HNSW index type with vector_cosine_ops operator class provides
sub-linear approximate nearest-neighbour search over the embedding column, which
is significantly faster than the default flat exact-scan for large tables.

Revision ID: 090
Revises: 089
"""

from alembic import op

revision = "090"
down_revision = "089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pattern_library_entries_embedding_hnsw "
        "ON pattern_library_entries USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_pattern_library_entries_embedding_hnsw")
