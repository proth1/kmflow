"""CLI entry point for the bulk evidence migration job.

Usage::

    python -m src.governance.migration_cli --engagement-id <UUID> [--dry-run]

The CLI creates an async database session, instantiates the storage backend
and Silver writer, then calls :func:`migrate_engagement` and prints a
human-readable summary to stdout.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from src.datalake.backend import LocalFilesystemBackend
from src.datalake.silver import SilverLayerWriter
from src.governance.migration import MigrationResult, migrate_engagement

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="migration_cli",
        description="Migrate existing evidence to Delta Lake medallion layers.",
    )
    parser.add_argument(
        "--engagement-id",
        required=True,
        help="UUID of the engagement to migrate.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate the migration without writing anything.",
    )
    parser.add_argument(
        "--storage-backend",
        choices=["local", "delta"],
        default="local",
        help="Storage backend type (default: local).",
    )
    parser.add_argument(
        "--base-path",
        default="evidence_store",
        help="Base path for local storage backend.",
    )
    parser.add_argument(
        "--datalake-path",
        default="datalake",
        help="Base path for the Silver writer.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level.",
    )
    return parser.parse_args(argv)


def _print_summary(result: MigrationResult) -> None:
    """Print a human-readable migration summary to stdout."""
    mode = "[DRY RUN] " if result.dry_run else ""
    print(f"\n{mode}Migration Summary for engagement: {result.engagement_id}")
    print("-" * 60)
    print(f"  Items processed:          {result.items_processed}")
    print(f"  Items skipped:            {result.items_skipped}")
    print(f"  Items failed:             {result.items_failed}")
    print(f"  Bronze writes:            {result.bronze_written}")
    print(f"  Silver writes:            {result.silver_written}")
    print(f"  Catalog entries created:  {result.catalog_entries_created}")
    print(f"  Lineage records created:  {result.lineage_records_created}")
    if result.errors:
        print(f"\n  Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"    - {err}")
    print()


async def _run(args: argparse.Namespace) -> int:
    """Create dependencies and execute the migration."""
    # Import here to avoid circular imports at module level
    from src.core.database import async_session_factory  # type: ignore[import-not-found]

    if args.storage_backend == "delta":
        from src.datalake.backend import DeltaLakeBackend
        storage = DeltaLakeBackend(base_path=args.base_path)
    else:
        storage = LocalFilesystemBackend(base_path=args.base_path)

    silver = SilverLayerWriter(base_path=args.datalake_path)

    async with async_session_factory() as session:
        result: MigrationResult = await migrate_engagement(
            session=session,
            engagement_id=args.engagement_id,
            storage_backend=storage,
            silver_writer=silver,
            dry_run=args.dry_run,
        )

    _print_summary(result)
    return 1 if result.items_failed > 0 else 0


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    args = _parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    exit_code = asyncio.run(_run(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
