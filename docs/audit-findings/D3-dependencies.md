# D3: Dependency & Regression Audit Findings

**Auditor**: D3 (Dependency & Regression Auditor)
**Date**: 2026-03-19
**Scope**: CVEs in dependencies, lock file status, abandoned packages, version pinning, supply chain security
**Prior Audit**: 2026-02-26 (this report supersedes and extends the prior findings)

---

## Summary

| Category | Count |
|---|---|
| CRITICAL findings | 0 |
| HIGH findings | 2 |
| MEDIUM findings | 6 |
| LOW findings | 5 |
| RESOLVED since last audit | 2 |

**Python dependency count (production)**: 27 packages in `[project.dependencies]` (3 added since last audit: pyopenssl, pyasn1, pypdf floors)
**Python lock file status**: STALE — `requirements.lock` present but reflects pyproject.toml state from PR #175 (2026-02); all subsequent CVE remediations updated pyproject.toml but did NOT regenerate the lock file. The lock contains `cryptography==43.0.3` while `pyproject.toml` requires `>=46.0.5`. This is an active discrepancy.
**Node.js lock file status**: PRESENT and UP TO DATE — `frontend/package-lock.json` (lockfileVersion 3); all three Cloudflare Worker packages have lock files.
**Docker images**: 9 services; 7 use pinned tags; 2 use floating minor-level tags; 1 uses untagged `:latest`.

---

## Resolved Findings (Since 2026-02-26)

### RESOLVED: recharts Declared But Not Imported

The prior audit flagged `recharts` as an unused production dependency. As of PR #622 (ingestion pipeline optimization), `recharts` is now used in `/frontend/src/app/assessment-matrix/page.tsx` for scatter chart visualizations. Finding is **closed**.

### RESOLVED: Next.js HTTP Request Smuggling (CVE-2026-29057)

PR #619 upgraded Next.js from 15.5.10 to 15.5.13, patching the moderate HTTP request smuggling vulnerability in rewrites. Finding is **closed**.

---

## Findings

### [HIGH] DEPENDENCY-MANAGEMENT: requirements.lock Is Stale — Locked cryptography Violates Declared Floor

**File**: `requirements.lock:30-34` and `pyproject.toml:54`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```
# requirements.lock:30-34 — version last compiled from pyproject.toml in PR #175 (Feb 2026)
cryptography==43.0.3
    # via
    #   kmflow (pyproject.toml)
    #   pdfminer-six
    #   pyjwt
```
```toml
# pyproject.toml:54 — floor raised to 46.0.5 in PR #613 (Mar 18, 2026)
"cryptography>=46.0.5,<48.0",
```
**Description**: The `requirements.lock` file was last regenerated in PR #175 (early Feb 2026) and has not been updated since. Six subsequent CVE remediation PRs (#175, #605, #613, #614, #615, #619) modified `pyproject.toml` but none regenerated the lock file. The most critical divergence: `pyproject.toml` declares `cryptography>=46.0.5` (required after bumping from 42.0.0 to remediate known CVEs), but `requirements.lock` specifies `cryptography==43.0.3`. Any toolchain that installs directly from the lock file will install a version 3 major releases behind the security floor. The lock file also omits `pyopenssl`, `pyasn1`, and `pypdf` entirely — three packages explicitly added to `pyproject.toml` as CVE floor guards in PR #613. The comment in `pyproject.toml:15` says "Run `pip freeze > requirements.lock` after any dependency change" but this has not been followed.
**Risk**: Any environment that uses `requirements.lock` for reproducible installs will install `cryptography==43.0.3`, which is below the security-remediated floor. CVEs fixed in the 44.x–46.x series of `cryptography` would be present. Additionally, the three CVE floor packages (pyopenssl, pyasn1, pypdf) would not be installed at all from the lock file.
**Recommendation**: Regenerate the lock file immediately: `uv pip compile pyproject.toml -o requirements.lock --generate-hashes`. Update `Dockerfile.backend:18` to use the lock file: `pip install --no-cache-dir --require-hashes -r requirements.lock`. Make lock file regeneration a required step in the dependency change checklist.

---

### [HIGH] DEPENDENCY-MANAGEMENT: Dockerfile.backend Does Not Use Lock File

**File**: `Dockerfile.backend:18`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```dockerfile
# Dockerfile.backend:18 — installs directly from pyproject.toml range specifiers
RUN pip install --no-cache-dir --prefix=/install "."
```
**Description**: The production Docker build resolves Python dependency versions at build time using `pyproject.toml` range specifiers, not from `requirements.lock`. This means two Docker builds at different times with the same source commit may produce different dependency trees. This finding was raised in the prior audit (2026-02-26) and remains unaddressed. It is elevated to HIGH because the stale lock file finding above (cryptography discrepancy) means the lock file also cannot be relied upon even if the Dockerfile were updated — both problems must be fixed together.
**Risk**: Non-deterministic production builds. Security-sensitive packages (cryptography, PyJWT, pdfplumber) can silently receive new minor/patch releases within their declared ranges. A compromised minor release within an allowed range would be automatically installed without a code review.
**Recommendation**: Fix the lock file (per finding above), then update `Dockerfile.backend:18` to: `COPY requirements.lock ./` and `RUN pip install --no-cache-dir --require-hashes -r requirements.lock`.

---

### [MEDIUM] CVE-EXPOSURE: Agent pyproject.toml Allows Vulnerable PyJWT Versions

**File**: `agent/python/pyproject.toml:13`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```toml
# agent/python/pyproject.toml:13
dependencies = [
    "httpx>=0.28.0",
    "PyJWT[crypto]>=2.9.0",
    "psutil>=5.9.0",
    "cryptography>=42.0.0",
]
```
**Description**: The desktop agent's `pyproject.toml` declares `PyJWT[crypto]>=2.9.0`, permitting any version from 2.9.0 onward. CVE-2026-32597 was fixed in PyJWT 2.12.1 (remediated in the main platform via PR #613 which raised the floor to `>=2.12.0`). The agent `requirements.txt` correctly pins `PyJWT[crypto]==2.12.1` with SHA-256 hashes, which protects builds that use that file. However, `pyproject.toml` remains the authoritative metadata for `pip install -e .` and `pip install kmflow-agent` scenarios, and it allows installation of the vulnerable range 2.9.0–2.11.x. The `cryptography` floor of `>=42.0.0` has a similar issue — the main platform floor was raised to `>=46.0.5` for security reasons, but the agent allows any version from 42.0.0.
**Risk**: A developer following `agent/python/pyproject.toml` for `pip install -e .` could install PyJWT 2.11.x (pre-CVE version) or cryptography 42.x–45.x (below the security floor set by the main platform). The agent handles JWT verification for authentication tokens from the backend — a vulnerable JWT library in this context is a meaningful attack surface.
**Recommendation**: Update `agent/python/pyproject.toml`: raise `PyJWT[crypto]>=2.12.0` and `cryptography>=46.0.5` to match the security floors established in the main `pyproject.toml`.

---

### [MEDIUM] LOCK-FILE-STALENESS: Python Lock File Does Not Include CVE Floor Packages

**File**: `requirements.lock` and `pyproject.toml:57-59`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```toml
# pyproject.toml:56-59 — added in PR #613 to pin CVE-patched transitive deps
# Transitive dep floors (CVE remediation — force minimum safe versions)
"pyopenssl>=26.0.0",
"pyasn1>=0.6.3",
"pypdf>=6.9.1",
```
**Description**: Three packages were explicitly added to `pyproject.toml` as transitive dependency floor guards after CVE remediation in PR #613 (2026-03-18). None of these packages appear in `requirements.lock` at all. If a developer uses `requirements.lock` to install dependencies (e.g., `pip install -r requirements.lock`), `pyopenssl`, `pyasn1`, and `pypdf` will not be installed — meaning the CVE floor guards that were added specifically for security are silently absent from any lock-file-based install. This is a direct consequence of the lock file not being regenerated after the CVE remediation.
**Risk**: CVE-2026-27448 and CVE-2026-27459 (pyopenssl), CVE-2026-30922 (pyasn1), CVE-2026-33123 (pypdf) — all patched in PR #613 — would be reintroduced in any environment that installs from `requirements.lock`. The CVE remediation is only effective if `pyproject.toml` is used directly for installation, which itself is non-deterministic.
**Recommendation**: Regenerate `requirements.lock` immediately after any `pyproject.toml` change. This is a process failure — the post-PR checklist must include lock file regeneration.

---

### [MEDIUM] COVERAGE-THRESHOLD: Enforcement Gate Inconsistent with Documented Standard

**File**: `pyproject.toml:114-115` and `.claude/rules/coding-standards.md:34`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```toml
# pyproject.toml:114-115
[tool.coverage.report]
fail_under = 70
```
```markdown
# .claude/rules/coding-standards.md:34
- Minimum 80% code coverage
```
**Description**: The coding standards document specifies 80% as the minimum coverage threshold, but the enforcement gate in `pyproject.toml` fails builds only below 70%. This means CI will pass a build at 71% coverage that violates the documented standard. Current actual coverage is 84% (per `coverage.json`), so there is no active violation today. However, as new code is added — particularly the newly untracked modules (`src/quality/`, `src/evaluation/`, `src/integrations/`) visible in git status — coverage could degrade to 75% without triggering a CI failure, silently breaking the policy.
**Risk**: Low-medium. No active violation today, but the gate will not catch policy regressions. New modules added without tests could erode coverage from 84% to below 80% without any CI signal.
**Recommendation**: Raise `fail_under` in `pyproject.toml` from `70` to `80` to align with the documented standard. Given actual coverage is at 84%, there is headroom to enforce the policy without breaking current CI.

---

### [MEDIUM] SUPPLY-CHAIN: Python Lock File Lacks Hash Verification

**File**: `requirements.lock:1-5` and `Dockerfile.backend:18`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```
# requirements.lock:1-3 — generated without --generate-hashes flag
# This file was autogenerated by uv via the following command:
#    uv pip compile pyproject.toml -o requirements.lock
aiofiles==24.1.0
```
**Description**: The `requirements.lock` file records pinned versions but no SHA-256 hashes. `npm`'s `package-lock.json` correctly includes SHA-512 integrity hashes for all 613 packages, providing tamper detection. The agent's `agent/python/requirements.txt` correctly uses `--hash=sha256:...` verification for all packages (4 direct + 8 transitive). The main platform lock file has no equivalent protection. This finding carries over from the prior audit (2026-02-26) and remains unaddressed.
**Risk**: Without hash verification, a compromised PyPI mirror or a man-in-the-middle attack could substitute a different package file during `pip install` without detection. All 27 production Python packages are exposed.
**Recommendation**: Regenerate with `uv pip compile pyproject.toml -o requirements.lock --generate-hashes`. Use `pip install --no-cache-dir --require-hashes -r requirements.lock` in `Dockerfile.backend`.

---

### [MEDIUM] LICENSE-COMPLIANCE: bpmn-js Watermark Preservation Not Verified Under Overlays

**File**: `frontend/package.json:27` and `frontend/src/components/BPMNViewer.tsx`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```typescript
// BPMNViewer.tsx — viewer mounts with overlays for confidence/evidence badges
const viewer = new BpmnJS({
  container: containerRef.current,
});
await viewer.importXML(bpmnXml);
const canvas = viewer.get("canvas") as any;
canvas.zoom("fit-viewport");
```
**Description**: `bpmn-js` v18.12.0 carries a modified MIT license (Camunda Services GmbH) requiring the bpmn.io watermark to remain fully visible and not visually overlapped at all times. `BPMNViewer.tsx` mounts the viewer and positions overlay elements (confidence badges, evidence count badges) on top of diagram elements. No visual regression test confirms the watermark is unobstructed in overlay states. This finding carries over from the prior audit with no remediation documented.
**Risk**: License violation. Camunda could require removal of the bpmn-js dependency or demand a commercial license under the Camunda Platform terms.
**Recommendation**: Add a visual QA checklist item: "Verify bpmn.io watermark is visible when confidence and evidence overlays are active." Document verification status in `BPMNViewer.tsx` JSDoc. Consider whether a Camunda commercial license is appropriate given KMFlow's proprietary commercial nature.

---

### [LOW] DOCKER-IMAGE: minio/mc Uses Floating Latest Tag

**File**: `docker-compose.yml`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```yaml
minio-init:
  image: minio/mc
  container_name: kmflow-minio-init
  security_opt:
    - no-new-privileges:true
```
**Description**: The `minio-init` service uses `image: minio/mc` with no version tag, which resolves to `:latest`. All other services in `docker-compose.yml` use pinned tags. This finding carries over from the prior audit unchanged.
**Risk**: Low. The service exits after bucket creation (`restart: "no"`). However, an unpinned image can pull a behaviorally different or compromised version on each `docker compose pull`.
**Recommendation**: Pin to a specific release tag matching the `minio/minio:RELEASE.2025-01-20T14-49-07Z` deployment.

---

### [LOW] DOCKER-IMAGE: Backend and Frontend Base Images Use Floating Minor Tags

**File**: `Dockerfile.backend:1` and `frontend/Dockerfile:1`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```dockerfile
# Dockerfile.backend:1
FROM python:3.12-slim AS builder

# frontend/Dockerfile:1
FROM node:20-alpine AS base
```
**Description**: Both base images use floating tags that advance with patch releases. This finding carries over from the prior audit unchanged.
**Risk**: Low for development; potential for base OS package changes between builds in production.
**Recommendation**: For production, use digest-pinned base images or explicit patch tags (e.g., `python:3.12.9-slim`).

---

### [LOW] DEPENDENCY-QUALITY: minimatch Override Required for Transitive CVE

**File**: `frontend/package.json:41-43`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```json
"overrides": {
  "minimatch": "^10.2.3"
}
```
**Description**: The override was updated from `^10.2.1` to `^10.2.3` in PR #615 to address CVE-2026-27903 (ReDoS in minimatch). The override remains necessary because one or more transitive dependencies still declare an old minimatch range. `npm audit` reports 0 vulnerabilities (confirming the override is effective).
**Risk**: Low. If the override is accidentally removed during a future upgrade, the CVE reactivates.
**Recommendation**: Add an inline comment identifying the transitive package requiring the old minimatch range, and the CVE it guards against. Check quarterly whether that transitive dependency has been updated upstream.

---

### [LOW] DEPENDENCY-QUALITY: Wrangler Version Inconsistency Across Workers

**File**: `infrastructure/cloudflare-workers/presentation-auth/package.json:13`, `state-street-apex-auth/package.json:14`, `tunnel-auth/package.json:13`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```json
// presentation-auth/package.json — locked to 4.65.0
"wrangler": "^4.65.0"

// state-street-apex-auth/package.json — locked to 4.69.0 (range ^4.65.0)
"wrangler": "^4.65.0"

// tunnel-auth/package.json — locked to 4.75.0
"wrangler": "^4.75.0"
```
**Description**: Three Cloudflare Worker packages use three different resolved versions of `wrangler` (4.65.0, 4.69.0, 4.75.0), reflecting separate lock file snapshots taken at different times. While each lock file pins an exact resolved version and lock files are committed, the range specifiers (`^4.65.0`, `^4.75.0`) mean running `npm install` in any of these directories could silently upgrade to a newer wrangler. Wrangler is a dev dependency but it drives deployments; version drift between workers risks inconsistent deployment behavior.
**Risk**: Low. Each worker has its own committed lock file so current builds are reproducible. The risk is only triggered by `npm install` (not `npm ci`).
**Recommendation**: Standardize all three workers to the same wrangler range (e.g., `^4.75.0`) and regenerate all lock files. Use `npm ci` in deployment scripts to prevent silent upgrades.

---

### [LOW] DEPENDENCY-QUALITY: langdetect at End of Active Maintenance

**File**: `pyproject.toml:48`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```toml
# pyproject.toml:48
# Language detection
"langdetect>=1.0.9,<2.0",
```
**Description**: `langdetect 1.0.9` is the most recent PyPI release. The package is a Python port of Google's language-detect library; the underlying algorithm has not been updated since 2021 (5+ years). No active security vulnerabilities are known, but the lack of maintenance means any discovered vulnerability would not receive a patch release. The package is functionally stable for language detection but represents growing technical debt if security issues emerge.
**Risk**: Low. No known CVEs. Risk is forward-looking: if a vulnerability is discovered, there is no active maintainer to issue a patch.
**Recommendation**: Monitor for a maintained alternative (e.g., `lingua-language-detector`, `fasttext-langdetect`) as a contingency. No action required today.

---

## Python Dependency Health Summary

| Package | Lock Version | Pyproject Range | CVE Status | Status |
|---|---|---|---|---|
| fastapi | 0.129.0 | >=0.115.0,<1.0 | None known | SAFE |
| uvicorn[standard] | 0.41.0 | >=0.32.0,<1.0 | None known | SAFE |
| sqlalchemy[asyncio] | 2.0.46 | >=2.0.36,<3.0 | None known | SAFE |
| asyncpg | 0.31.0 | >=0.30.0,<1.0 | None known | SAFE |
| alembic | 1.18.4 | >=1.14.0,<2.0 | None known | SAFE |
| pgvector | 0.4.2 | >=0.3.6,<1.0 | None known | SAFE |
| neo4j | 5.28.3 | >=5.27.0,<6.0 | None known | SAFE |
| redis[hiredis] | 5.3.1 | >=5.2.0,<6.0 | None known | SAFE |
| pydantic | 2.12.5 | >=2.10.0,<3.0 | None known | SAFE |
| pydantic-settings | 2.13.1 | >=2.7.0,<3.0 | None known | SAFE |
| pyyaml | 6.0.3 | >=6.0,<7.0 | None known | SAFE |
| python-dotenv | 1.2.1 | >=1.0.1,<2.0 | None known | SAFE |
| httpx | 0.28.1 | >=0.28.0,<1.0 | None known | SAFE |
| python-multipart | 0.0.22 | >=0.0.22,<1.0 | None known | SAFE |
| aiofiles | 24.1.0 | >=24.1.0 | None known | LOW (no upper bound) |
| slowapi | 0.1.9 | >=0.1.9,<1.0 | None known | SAFE |
| python-magic | 0.4.27 | >=0.4.27,<1.0 | None known | SAFE |
| python-docx | 1.2.0 | >=1.1.0,<2.0 | None known | SAFE |
| pdfplumber | 0.11.9 | >=0.11.0,<1.0 | None known | SAFE |
| openpyxl | 3.1.5 | >=3.1.0,<4.0 | None known | SAFE |
| lxml | 5.4.0 | >=5.0.0,<6.0 | None known | SAFE |
| defusedxml | 0.7.1 | >=0.7.0,<1.0 | None known | SAFE |
| numpy | 2.4.2 | >=1.26.0,<3.0 | None known | SAFE |
| PyJWT[crypto] | 2.11.0 (lock) | >=2.12.0,<3.0 | CVE-2026-32597 fixed in 2.12.1 | HIGH: lock file stale |
| bcrypt | 4.3.0 | >=4.0.0,<5.0 | None known | SAFE |
| cryptography | 43.0.3 (lock) | >=46.0.5,<48.0 | Lock violates floor | HIGH: lock file stale |
| email-validator | 2.3.0 | >=2.0.0,<3.0 | None known | SAFE |
| pyopenssl | NOT IN LOCK | >=26.0.0 | CVE-2026-27448, CVE-2026-27459 — floor guards absent from lock | HIGH: missing from lock |
| pyasn1 | NOT IN LOCK | >=0.6.3 | CVE-2026-30922 — floor guard absent from lock | HIGH: missing from lock |
| pypdf | NOT IN LOCK | >=6.9.1 | CVE-2026-33123 — floor guard absent from lock | HIGH: missing from lock |
| pillow | 12.1.1 (transitive) | NOT DECLARED | None known | MEDIUM: undeclared direct dep |
| opencv-python (cv2) | NOT IN LOCK | NOT DECLARED | None known | MEDIUM: undeclared |
| sentence-transformers | NOT IN LOCK | NOT DECLARED | None known | MEDIUM: undeclared (in [ml] extra docs only) |
| langdetect | 1.0.9 | >=1.0.9,<2.0 | None known | LOW: maintenance risk |

---

## Accepted Risks (Documented)

| Advisory | Severity | Package | Decision | Review Date |
|---|---|---|---|---|
| CVE-2024-23342 | MEDIUM | ecdsa (via python-jose) | Accept — python-jose removed; ecdsa no longer in dependency graph | 2026-03-12 |
| GHSA-3x4c-7xq6-9pq8 | Moderate | next (image cache) | Accept — no `remotePatterns` configured; not exploitable | 2026-03-18 |
| GHSA-vpq2-c234-7xj6 | Low | @tootallnate/once | Accept — dev dependency only, no production exposure | 2026-03-12 |

Note: The `docs/security/accepted-risks.md` entry for CVE-2024-23342 references `python-jose` as the transitive path. `python-jose` is not present in `requirements.lock` or `pyproject.toml`, indicating it was removed. The accepted-risks document should be updated to reflect this.

---

## Docker Image Pinning Summary

| Service | Image | Pinned | Notes |
|---|---|---|---|
| postgres | pgvector/pgvector:0.8.0-pg15 | Yes | Specific version |
| neo4j | neo4j:5.25-community | Yes | Specific version |
| redis | redis:7.4-alpine | Yes | Minor+patch pinned |
| cib7 | cibseven/cibseven:run-2.1.0 | Yes | Specific version |
| minio | minio/minio:RELEASE.2025-01-20T14-49-07Z | Yes | Timestamped release |
| minio-init | minio/mc | NO | Floating :latest |
| mailpit | axllent/mailpit:v1.22 | Yes | Specific version |
| backend | python:3.12-slim | Partial | Floating patch level |
| frontend | node:20-alpine | Partial | Floating patch level |

---

## Supply Chain Risk Score: MEDIUM-HIGH

The JavaScript supply chain is in good shape: all three Cloudflare Worker packages and the frontend have committed lock files with integrity hashes; two accepted npm advisories are documented and non-exploitable; Next.js CVE was patched same-day.

The Python supply chain has an active process gap: `requirements.lock` has not been regenerated since PR #175 (early February) despite six subsequent dependency updates including multiple CVE remediations. The lock file currently specifies `cryptography==43.0.3` while `pyproject.toml` requires `>=46.0.5`, and three CVE floor packages are absent from the lock entirely. Because `Dockerfile.backend` does not use the lock file, the production build is not affected by this discrepancy today — but the lock file cannot be trusted as a reproducible build artifact until it is regenerated. Regenerating the lock file and wiring it into the Dockerfile would resolve both HIGH findings.
