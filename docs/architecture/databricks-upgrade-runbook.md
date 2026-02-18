# Databricks Upgrade Runbook

This runbook covers upgrading KMFlow from local or Delta Lake storage to
Databricks Volumes (Unity Catalog). After following these steps, switching
between backends requires only a configuration change — no code changes.

---

## Prerequisites

### Databricks workspace
- Databricks Runtime 13.3 LTS or later (for Unity Catalog Volumes support)
- Unity Catalog enabled on the metastore
- A Unity Catalog catalog already created (default name: `kmflow`)

### Service principal
Create a service principal that KMFlow will authenticate as:

1. In your Databricks account console, go to **Service principals** and
   create a new principal named `kmflow-api`.
2. Assign it the following workspace-level permissions:
   - **Can use** on the target SQL warehouse
3. Assign the following Unity Catalog privileges (on the `kmflow` catalog):
   - `USE CATALOG`, `USE SCHEMA`, `CREATE SCHEMA` (on the catalog)
   - `CREATE TABLE`, `MODIFY`, `SELECT` (on each schema)
   - `READ VOLUME`, `WRITE VOLUME` (on the target volume)
4. Generate an OAuth token or personal access token for the principal and
   store it securely (e.g., in AWS Secrets Manager, Azure Key Vault, or
   your secrets management tool of choice).

### Unity Catalog objects
Create the following objects before running KMFlow with the Databricks backend.
Run these SQL statements in the Databricks SQL editor or via the CLI:

```sql
-- Create catalog (skip if already exists)
CREATE CATALOG IF NOT EXISTS kmflow;

-- Create schemas (medallion layers)
CREATE SCHEMA IF NOT EXISTS kmflow.evidence_bronze;
CREATE SCHEMA IF NOT EXISTS kmflow.evidence_silver;
CREATE SCHEMA IF NOT EXISTS kmflow.evidence_gold;

-- Create the volume for raw file storage
CREATE VOLUME IF NOT EXISTS kmflow.evidence.raw_evidence;

-- Create the metadata tracking table
CREATE TABLE IF NOT EXISTS `kmflow`.`evidence`.`evidence_metadata` (
    id             STRING        NOT NULL,
    engagement_id  STRING        NOT NULL,
    file_name      STRING        NOT NULL,
    volume_path    STRING        NOT NULL,
    content_hash   STRING        NOT NULL,
    size_bytes     BIGINT        NOT NULL,
    stored_at      STRING        NOT NULL,
    metadata_json  STRING,
    CONSTRAINT pk_evidence_metadata PRIMARY KEY (id)
)
USING DELTA;
```

### Python dependencies
Install the Databricks extras group:

```bash
pip install 'kmflow[databricks]'
# This installs: databricks-sdk>=0.20.0
```

---

## Configuration changes

All configuration is controlled via environment variables. No code changes
are required to switch backends.

### Required variables

| Variable | Description | Example |
|---|---|---|
| `STORAGE_BACKEND` | Select the Databricks backend | `databricks` |
| `DATABRICKS_HOST` | Workspace URL | `https://adb-1234567890.12.azuredatabricks.net` |
| `DATABRICKS_TOKEN` | Service principal token | `dapiXXXXXXXXXXXXXXXXXXXX` |

### Optional variables (with defaults)

| Variable | Default | Description |
|---|---|---|
| `DATABRICKS_CATALOG` | `kmflow` | Unity Catalog catalog name |
| `DATABRICKS_SCHEMA` | `evidence` | Base schema name (layer suffix added automatically) |
| `DATABRICKS_VOLUME` | `raw_evidence` | Volume name for file storage |

### Example `.env` file

```dotenv
# Storage backend
STORAGE_BACKEND=databricks

# Databricks workspace
DATABRICKS_HOST=https://adb-1234567890.12.azuredatabricks.net
DATABRICKS_TOKEN=dapiXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

# Unity Catalog coordinates
DATABRICKS_CATALOG=kmflow
DATABRICKS_SCHEMA=evidence
DATABRICKS_VOLUME=raw_evidence
```

### Docker / Kubernetes
Pass the variables as container environment variables or Kubernetes Secrets.
Do not bake credentials into Docker images.

---

## Migration steps

Run these steps to migrate existing evidence files from local or Delta Lake
storage to Databricks Volumes.

### Step 1 — Inventory existing files

```bash
# List all evidence files under the current store
find ./evidence_store -type f | sort > /tmp/migration-inventory.txt
wc -l /tmp/migration-inventory.txt
```

### Step 2 — Run the migration script

A migration script is provided in `scripts/migrate_to_databricks.py`.
Set the environment variables for the **target** Databricks workspace, then:

```bash
python scripts/migrate_to_databricks.py \
  --source-dir ./evidence_store \
  --catalog kmflow \
  --schema evidence \
  --volume raw_evidence \
  --dry-run           # remove this flag to execute
```

The script uploads each file using `DatabricksBackend.write()` so all
metadata rows are tracked in the `evidence_metadata` Delta table.

### Step 3 — Register Unity Catalog tables

After migrating files, register all `DataCatalogEntry` records as Unity
Catalog tables. The `register_tables` function in
`src/governance/unity_catalog.py` handles this bulk operation:

```python
from databricks.sdk import WorkspaceClient
from src.governance.unity_catalog import register_tables
from src.core.models import DataCatalogEntry
# ... load entries from your database session ...

client = WorkspaceClient(
    host="https://adb-1234567890.12.azuredatabricks.net",
    token="dapi...",
)
results = register_tables(
    client,
    catalog_entries=entries,
    catalog="kmflow",
    schema="evidence",
    warehouse_id="your-sql-warehouse-id",
)
print(results)
```

### Step 4 — Verify migration

```bash
# Count files uploaded to Volumes
python - <<'EOF'
from databricks.sdk import WorkspaceClient
import os

w = WorkspaceClient(
    host=os.environ["DATABRICKS_HOST"],
    token=os.environ["DATABRICKS_TOKEN"],
)
entries = list(w.files.list_directory_contents("/Volumes/kmflow/evidence/raw_evidence/evidence_store"))
print(f"Files in Volumes: {len(entries)}")
EOF
```

Compare the count to the inventory from Step 1. If counts match, proceed.

---

## Validation checklist

After deployment, verify each item:

- [ ] `GET /api/v1/health` returns `200 OK` with `"storage": "databricks"`
- [ ] Upload a test evidence file via `POST /api/v1/evidence/upload`
      and confirm it appears in the Databricks Volumes UI
- [ ] `GET /api/v1/evidence/{engagement_id}` returns the uploaded file
- [ ] Run the test suite against the staging environment:
      `pytest tests/datalake/test_databricks_backend.py -v`
- [ ] Confirm the `evidence_metadata` Delta table has new rows
      (query via Databricks SQL editor: `SELECT * FROM kmflow.evidence.evidence_metadata LIMIT 5`)
- [ ] Verify Unity Catalog table registrations exist under the correct schemas
- [ ] Confirm the service principal has no overly broad permissions
      (audit via `SHOW GRANTS ON CATALOG kmflow`)

---

## Rollback procedure

If the Databricks backend is unstable, roll back to the previous backend by
updating one environment variable — no deployment is required if the
application reads configuration at startup.

### Immediate rollback

```bash
# In your deployment environment (ECS, Kubernetes, etc.):
STORAGE_BACKEND=local   # or "delta" if using DeltaLakeBackend
# Restart the API service to pick up the new value
```

### Full rollback steps

1. **Revert environment variable**: Set `STORAGE_BACKEND` back to `local`
   or `delta`.
2. **Restart API pods/containers** so they pick up the configuration change.
3. **Verify health endpoint**: `GET /api/v1/health` should show the
   reverted backend.
4. **Do not delete Databricks data**: Files in Volumes and the metadata
   Delta table are safe to keep — they will not be accessed while the
   Databricks backend is inactive. This gives you a re-migration path if
   you want to switch back.
5. **Notify stakeholders** of the rollback and expected root-cause timeline.

### Data consistency after rollback

Files uploaded while the Databricks backend was active are **not**
automatically copied back to local storage. If the rollback period is short,
you may choose to hold new uploads until Databricks is re-enabled. For longer
rollbacks, re-run the migration script in reverse:

```bash
python scripts/migrate_from_databricks.py \
  --catalog kmflow \
  --schema evidence \
  --volume raw_evidence \
  --target-dir ./evidence_store
```

---

## Troubleshooting

### `ImportError: databricks-sdk is required`
The `databricks-sdk` package is not installed. Run:
```bash
pip install 'kmflow[databricks]'
```

### `RESOURCE_DOES_NOT_EXIST` on volume operations
The Unity Catalog volume does not exist. Re-run the prerequisite SQL to
create it: `CREATE VOLUME IF NOT EXISTS kmflow.evidence.raw_evidence;`

### `PERMISSION_DENIED` on write
The service principal lacks `WRITE VOLUME` on the target volume. Grant:
```sql
GRANT WRITE VOLUME ON VOLUME kmflow.evidence.raw_evidence TO `kmflow-api`;
```

### Files appear in Volumes but not in the metadata table
A SQL warehouse was not running when the write occurred (the metadata insert
is best-effort). The files are safely stored. To backfill the metadata table,
query the Volumes directory and insert missing rows manually, or re-run the
migration script in idempotent mode (`--backfill-metadata`).

### Metadata table rows duplicated
The `write()` method generates a unique `record_id` per call so duplicates
should not occur under normal operation. If duplicates appear, check whether
multiple application instances are processing the same upload event (at-least-once
delivery). The `id` primary key constraint will surface the conflict; deduplicate
by keeping the row with the earliest `stored_at`.
