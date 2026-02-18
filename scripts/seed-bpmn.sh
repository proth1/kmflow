#!/usr/bin/env bash
# Deploy all KMFlow BPMN process models to CIB7
# Usage: ./scripts/seed-bpmn.sh [CIB7_URL]

set -euo pipefail

CIB7_URL="${1:-http://localhost:8080/engine-rest}"

echo "Deploying BPMN models to CIB7 at $CIB7_URL..."

# Wait for CIB7 to be ready
for i in $(seq 1 30); do
  if curl -sf "$CIB7_URL/engine" > /dev/null 2>&1; then
    echo "CIB7 is ready"
    break
  fi
  echo "Waiting for CIB7... ($i/30)"
  sleep 2
done

# Deploy each BPMN file from platform/
DEPLOYED=0
FAILED=0

for bpmn_file in platform/*.bpmn platform/templates/*.bpmn; do
  [ -f "$bpmn_file" ] || continue
  name=$(basename "$bpmn_file" .bpmn)
  echo -n "  Deploying $name... "

  response=$(curl -sf -w "%{http_code}" \
    -X POST "$CIB7_URL/deployment/create" \
    -F "deployment-name=$name" \
    -F "enable-duplicate-filtering=true" \
    -F "data=@$bpmn_file" 2>/dev/null) || true

  http_code="${response: -3}"
  if [ "$http_code" = "200" ]; then
    echo "OK"
    DEPLOYED=$((DEPLOYED + 1))
  else
    echo "FAILED (HTTP $http_code)"
    FAILED=$((FAILED + 1))
  fi
done

echo ""
echo "Deployment complete: $DEPLOYED succeeded, $FAILED failed"
