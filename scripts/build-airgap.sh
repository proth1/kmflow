#!/usr/bin/env bash
# Air-gapped build script (KMFLOW-7)
#
# Produces Docker images and a vendored Python dependency archive that
# can be transferred to an isolated network via `docker load` and
# pip install from local wheels.
#
# Output directory: ./airgap-bundle/
#
# Usage:
#   ./scripts/build-airgap.sh
#   # Transfer airgap-bundle/ to target environment
#   # On target: docker load < airgap-bundle/images.tar
#   # On target: pip install --no-index --find-links=airgap-bundle/wheels/ kmflow

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUNDLE_DIR="$PROJECT_DIR/airgap-bundle"
MANIFEST="$BUNDLE_DIR/manifest.json"

echo "=== KMFlow Air-Gapped Build ==="
echo "Project: $PROJECT_DIR"
echo "Bundle:  $BUNDLE_DIR"
echo ""

# Clean previous bundle
rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR/wheels"

# ── Step 1: Vendor Python dependencies ─────────────────────
echo "[1/5] Vendoring Python dependencies..."
pip download \
    -r "$PROJECT_DIR/requirements.txt" \
    --dest "$BUNDLE_DIR/wheels" \
    --no-cache-dir \
    2>/dev/null || pip download \
    "$PROJECT_DIR" \
    --dest "$BUNDLE_DIR/wheels" \
    --no-cache-dir

echo "  $(ls "$BUNDLE_DIR/wheels" | wc -l | tr -d ' ') wheels downloaded"

# ── Step 2: Build Docker images ────────────────────────────
echo "[2/5] Building Docker images..."
cd "$PROJECT_DIR"

# Build backend
docker build \
    -f Dockerfile.backend \
    -t kmflow-backend:airgap \
    --build-arg PIP_NO_CACHE_DIR=1 \
    . 2>/dev/null

# Build frontend
docker build \
    -f frontend/Dockerfile \
    --target runner \
    -t kmflow-frontend:airgap \
    frontend/ 2>/dev/null

echo "  Images built: kmflow-backend:airgap, kmflow-frontend:airgap"

# ── Step 3: Save images to tarball ─────────────────────────
echo "[3/5] Saving Docker images to tarball..."
docker save \
    kmflow-backend:airgap \
    kmflow-frontend:airgap \
    pgvector/pgvector:0.8.0-pg15 \
    neo4j:5.25-community \
    redis:7.4-alpine \
    ollama/ollama:latest \
    cibseven/cibseven:run-2.1.0 \
    minio/minio \
    | gzip > "$BUNDLE_DIR/images.tar.gz"

echo "  Tarball: $(du -sh "$BUNDLE_DIR/images.tar.gz" | cut -f1)"

# ── Step 4: Copy deployment configs ───────────────────────
echo "[4/5] Copying deployment configs..."
cp "$PROJECT_DIR/docker-compose.yml" "$BUNDLE_DIR/"
cp "$PROJECT_DIR/docker-compose.on-prem.yaml" "$BUNDLE_DIR/"
cp "$PROJECT_DIR/.env.example" "$BUNDLE_DIR/.env.example" 2>/dev/null || true

# Copy Alembic migrations for database setup
cp -r "$PROJECT_DIR/alembic" "$BUNDLE_DIR/alembic"
cp "$PROJECT_DIR/alembic.ini" "$BUNDLE_DIR/"

# ── Step 5: Generate manifest ─────────────────────────────
echo "[5/5] Generating manifest..."
python3 -c "
import hashlib, json, os, datetime

bundle_dir = '$BUNDLE_DIR'
manifest = {
    'build_date': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'version': open('$PROJECT_DIR/.current-version').read().strip(),
    'images': {},
    'wheels': {},
    'configs': [],
}

# Hash images tarball
tarball = os.path.join(bundle_dir, 'images.tar.gz')
if os.path.exists(tarball):
    h = hashlib.sha256()
    with open(tarball, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    manifest['images']['tarball'] = {
        'file': 'images.tar.gz',
        'sha256': h.hexdigest(),
        'size_bytes': os.path.getsize(tarball),
    }

# Hash wheels
wheels_dir = os.path.join(bundle_dir, 'wheels')
for whl in sorted(os.listdir(wheels_dir)):
    path = os.path.join(wheels_dir, whl)
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    manifest['wheels'][whl] = h.hexdigest()

# List configs
for cfg in ['docker-compose.yml', 'docker-compose.on-prem.yaml', '.env.example']:
    if os.path.exists(os.path.join(bundle_dir, cfg)):
        manifest['configs'].append(cfg)

with open('$MANIFEST', 'w') as f:
    json.dump(manifest, f, indent=2)

print(f'  Manifest: {len(manifest[\"wheels\"])} wheels, {len(manifest[\"configs\"])} configs')
"

echo ""
echo "=== Build Complete ==="
echo "Bundle contents:"
du -sh "$BUNDLE_DIR"/*
echo ""
echo "Transfer airgap-bundle/ to the target environment, then:"
echo "  gunzip -c images.tar.gz | docker load"
echo "  docker compose -f docker-compose.yml -f docker-compose.on-prem.yaml up -d"
