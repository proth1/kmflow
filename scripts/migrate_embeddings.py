#!/usr/bin/env python3
"""Re-embed all existing evidence fragments with the new embedding model.

Migrates from all-mpnet-base-v2 (768-dim) to nomic-embed-text-v1.5 (768-dim).
Since both models produce 768-dimensional vectors, no pgvector column migration
is needed — we just regenerate and overwrite the embeddings.

Usage:
    python scripts/migrate_embeddings.py [--batch-size 32] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def migrate_embeddings(batch_size: int = 32, dry_run: bool = False) -> None:
    """Re-embed all fragments using the new model."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from src.core.config import get_settings
    from src.rag.embeddings import EmbeddingService

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)

    embedding_service = EmbeddingService()
    logger.info("Using embedding model: %s", embedding_service.model_name)

    async with AsyncSession(engine) as session:
        # Count total fragments
        count_result = await session.execute(
            text("SELECT count(*) FROM evidence_fragments WHERE content IS NOT NULL AND content != ''")
        )
        total = count_result.scalar() or 0
        logger.info("Total fragments to re-embed: %d", total)

        if dry_run:
            logger.info("DRY RUN — no changes will be made")
            return

        # Process in batches
        offset = 0
        processed = 0

        while offset < total:
            result = await session.execute(
                text(
                    "SELECT id::text, content FROM evidence_fragments "
                    "WHERE content IS NOT NULL AND content != '' "
                    "ORDER BY created_at "
                    "LIMIT :batch_size OFFSET :offset"
                ),
                {"batch_size": batch_size, "offset": offset},
            )
            rows = result.fetchall()

            if not rows:
                break

            texts = [row[1] for row in rows]
            fragment_ids = [row[0] for row in rows]

            # Generate embeddings
            embeddings = await embedding_service.generate_embeddings_async(texts, batch_size=batch_size)

            # Store embeddings
            for frag_id, embedding in zip(fragment_ids, embeddings, strict=True):
                vector_str = "[" + ",".join(str(v) for v in embedding) + "]"
                await session.execute(
                    text("UPDATE evidence_fragments SET embedding = :embedding WHERE id = :frag_id::uuid"),
                    {"embedding": vector_str, "frag_id": frag_id},
                )

            await session.commit()
            processed += len(rows)
            offset += batch_size

            logger.info("Progress: %d/%d fragments re-embedded (%.1f%%)", processed, total, processed / total * 100)

    logger.info("Migration complete: %d fragments re-embedded with %s", processed, embedding_service.model_name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-embed all fragments with new model")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size for embedding generation")
    parser.add_argument("--dry-run", action="store_true", help="Count fragments without making changes")
    args = parser.parse_args()

    asyncio.run(migrate_embeddings(batch_size=args.batch_size, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
