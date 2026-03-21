# D3: Dependency & Regression Audit Findings

**Auditor**: D3 (Dependency & Regression Auditor)
**Date**: 2026-03-20
**Scope**: CVEs in dependencies, lock file status, abandoned packages, version pinning, supply chain security
**Prior Audit**: 2026-03-19 (this report supersedes and extends the prior findings)

---

## Summary

| Category | Count |
|---|---|
| CRITICAL findings | 0 |
| HIGH findings | 0 |
| MEDIUM findings | 0 |
| LOW findings | 5 |
| RESOLVED since last audit | 8 (0 new this cycle) |

**Python dependency count (production)**: 27 packages in `[project.dependencies]` (pyopenssl, pyasn1 present as CVE floor guards)
**Python lock file status**: CURRENT — `requirements.lock` regenerated with `uv pip compile pyproject.toml -o requirements.lock --generate-hashes`. SHA-256 hashes present for all packages. `cryptography==46.0.5`, `pyjwt==2.12.1`, `pyopenssl==26.0.0`, and `pyasn1==0.6.3` all correctly pinned in the lock.
**Node.js lock file status**: PRESENT — `frontend/package-lock.json` (lockfileVersion 3, up to date); all three Cloudflare Worker packages have committed lock files. Note: all three worker lock root entries still show `"jose": "^6.1.3"` (caret) rather than the exact pin `"6.1.3"` declared in `package.json` — lock files were not regenerated after the pin change (see LOW finding LOCK-FILE below).
**Docker install method**: `Dockerfile.backend:20` installs via `pip install --no-cache-dir --require-hashes --prefix=/install -r requirements.lock` — hash verification active on all Docker builds.

---

## Resolved Findings (Since 2026-02-26)

### RESOLVED: recharts Declared But Not Imported

The prior audit flagged `recharts` as an unused production dependency. As of PR #622 (ingestion pipeline optimization), `recharts` is now used in `/frontend/src/app/assessment-matrix/page.tsx`. Finding is **closed**.

### RESOLVED: Next.js HTTP Request Smuggling (CVE-2026-29057)

PR #619 upgraded Next.js from 15.5.10 to 15.5.13. Finding is **closed**.

### RESOLVED: Agent pyproject.toml PyJWT and cryptography Floor Too Low

The prior audit flagged `agent/python/pyproject.toml` as declaring `PyJWT[crypto]>=2.9.0` and `cryptography>=42.0.0`. The current file correctly specifies `PyJWT[crypto]>=2.12.0` and `cryptography>=46.0.5`, matching the main platform floors. Finding is **closed**.

### RESOLVED: Coverage Threshold Below Documented Standard

A prior finding noted `fail_under = 70` in `pyproject.toml` against the documented 80% standard. The current `pyproject.toml` specifies `fail_under = 90`, exceeding the standard. Finding is **closed**.

---

## Resolved Findings (Since 2026-03-19)

### RESOLVED: [HIGH] requirements.lock Is Stale — Locked Versions Violate Declared Security Floors

The prior audit (2026-03-19) found `requirements.lock` containing `cryptography==43.0.3` (floor `>=46.0.5`) and `pyjwt==2.11.0` (floor `>=2.12.0`), while `Dockerfile.backend` installed directly from the stale lock. The lock file has been regenerated: header line 2 now reads `uv pip compile pyproject.toml -o requirements.lock --generate-hashes`. Verified resolved versions: `cryptography==46.0.5` (line 349), `pyjwt==2.12.1` (line 1230). Finding is **closed**.

### RESOLVED: [HIGH] requirements.lock Lacks Hash Verification

The prior audit found the lock file compiled without `--generate-hashes` and `Dockerfile.backend` installing without `--require-hashes`. Both are now corrected: the lock contains SHA-256 hashes for all packages and `Dockerfile.backend:20` uses `pip install --no-cache-dir --require-hashes --prefix=/install -r requirements.lock`. Finding is **closed**.

### RESOLVED: [MEDIUM] Python Lock File Does Not Include CVE Floor Packages

The prior audit found `pyopenssl` and `pyasn1` (added to `pyproject.toml` as transitive CVE floor guards in PR #613) entirely absent from `requirements.lock`. Both are now present: `pyopenssl==26.0.0` (line 1236), `pyasn1==0.6.3` (line 1088). Finding is **closed**.

### RESOLVED: [MEDIUM] Worker package.json Files Use Caret Ranges for jose

The prior audit found all three Cloudflare Worker `package.json` files using `"jose": "^6.1.3"` (caret range on the auth-critical JWT library). All three workers now use exact pin `"jose": "6.1.3"`: `infrastructure/cloudflare-workers/presentation-auth/package.json:16`, `state-street-apex-auth/package.json:16`, `tunnel-auth/package.json:9`. Finding is **closed**. Note: a cycle 7 inspection found that the lock files were not regenerated after the pin change — all three lock root entries still show `"^6.1.3"`. This is tracked as a separate new LOW finding (LOCK-FILE).

### RESOLVED: [MEDIUM] aiofiles Declared Without Upper Bound

The prior audit found `pyproject.toml` declaring `"aiofiles>=24.1.0"` with no upper major cap, inconsistent with all other production dependencies. The declaration now reads `"aiofiles>=24.1.0,<26.0"` (`pyproject.toml:38`). Finding is **closed**.

### RESOLVED: [LOW] minio/mc Uses Floating Latest Tag

The prior audit found the `minio-init` service using `image: minio/mc` with no version tag. The `docker-compose.yml` now pins `image: minio/mc:RELEASE.2025-01-20T17-06-52Z` (line 150). Finding is **closed**.

### RESOLVED: [LOW] Backend and Frontend Base Images Use Floating Minor Tags

The prior audit found `Dockerfile.backend` using `python:3.12-slim` (floating patch) and `frontend/Dockerfile` using `node:20-alpine` (floating patch). Both are now patch-level pinned: `python:3.12.11-slim` (`Dockerfile.backend:2`, `Dockerfile.backend:23`) and `node:20.19-alpine` (`frontend/Dockerfile:2`). Finding is **closed**.

---

## Findings

### [LOW] DOCKER-IMAGE: Neo4j Image Uses Minor-Only Tag

**File**: `docker-compose.yml:31`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```yaml
# docker-compose.yml:31
neo4j:
  image: neo4j:5.27-community
```
**Description**: The Neo4j service is pinned to minor version `5.27` but not to a patch release. The `5.27-community` tag advances with patch releases (e.g., `5.27.0` → `5.27.1`), meaning `docker compose pull` can silently change the running version. All other services that do not use timestamped releases (postgres, redis, cib7, minio, mailpit) are pinned to specific patch versions. Neo4j is the exception.
**Risk**: Low. Neo4j 5.x patch releases are generally backwards-compatible. The risk is a behavioral change or regression introduced by an upstream patch being pulled in without an explicit version bump in the compose file.
**Recommendation**: Pin to a specific patch release (e.g., `neo4j:5.27.0-community`) or use the current resolved patch tag. Check `docker inspect kmflow-neo4j` to determine the current running patch version, then pin to it.

---

### [LOW] DEPENDENCY-QUALITY: minimatch Override Lacks Identifying Comment

**File**: `frontend/package.json:41-43`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```json
"overrides": {
  "minimatch": "^10.2.3"
}
```
**Description**: An override forces `minimatch>=10.2.3` to address CVE-2026-27903 (ReDoS). The override is effective — `package-lock.json` resolves `minimatch@10.2.4` and `npm audit` reports 0 vulnerabilities. However, there is no inline comment identifying which transitive dependency requires the old minimatch range and which CVE the override guards against. If the override is accidentally removed in a future `package.json` change, the CVE silently reactivates with no audit trail.
**Risk**: Low. Current state is safe. Risk is forward-looking.
**Recommendation**: Add an inline comment (using the `"//"` JSON comment convention already in use at `package.json:18`) identifying the CVE and the dependency chain that requires the override. Check quarterly whether the upstream dependency has been updated to use a safe minimatch version.

---

### [LOW] DEPENDENCY-QUALITY: Wrangler Caret Ranges and Version Inconsistency Across Workers

**File**: `infrastructure/cloudflare-workers/presentation-auth/package.json:13`, `state-street-apex-auth/package.json:14`, `tunnel-auth/package.json:13`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```json
// presentation-auth/package.json — caret range; lock resolves to 4.65.0
"wrangler": "^4.65.0"

// state-street-apex-auth/package.json — same range; lock resolves to 4.69.0
"wrangler": "^4.65.0"

// tunnel-auth/package.json — different range; lock resolves to 4.75.0
"wrangler": "^4.75.0"
```
**Description**: All three Cloudflare Worker `package.json` files use caret ranges for `wrangler` (the deployment tool). The caret ranges contradict the exact-pin ADR. Additionally, the three workers resolve to three different `wrangler` versions (4.65.0, 4.69.0, 4.75.0), meaning deployment behavior may diverge between workers. Each worker has a committed lock file so individual builds are reproducible, but running `npm install` instead of `npm ci` would silently upgrade to whatever the range resolves to at that moment.
**Risk**: Low. Each lock file ensures reproducibility for `npm ci`. Risk only materializes on fresh installs or when lock files are regenerated independently.
**Recommendation**: Standardize all three workers to `"wrangler": "4.75.0"` (exact pin) and regenerate all lock files. Use `npm ci` in all deployment scripts.

---

### [LOW] LOCK-FILE: Worker Lock Root Entries Inconsistent With Declared jose Exact Pin

**File**: `infrastructure/cloudflare-workers/presentation-auth/package-lock.json`, `state-street-apex-auth/package-lock.json`, `tunnel-auth/package-lock.json`
**Agent**: D3 (Dependency & Regression Auditor)
**Evidence**:
```json
// Root entry in all three lock files (stale — reflects pre-pin-change package.json state)
"jose": "^6.1.3"

// Current declaration in all three package.json files (correct — exact pin)
"jose": "6.1.3"

// Resolved node_modules/jose version in all three lock files (correct)
"version": "6.1.3"
```
**Description**: The three Cloudflare Worker `package.json` files were updated to declare `"jose": "6.1.3"` (exact pin), resolving the prior MEDIUM finding. However, the lock files were not regenerated after this change. The root package entries in all three lock files still show `"jose": "^6.1.3"` (the caret range from before the pin change). The `node_modules/jose` resolved version in each lock is `6.1.3`, so there is no security exposure when using `npm ci`. The discrepancy indicates the lock files were not regenerated after the `package.json` exact-pin change and are now inconsistent with the declared intent.
**Risk**: Low. No current security exposure — the lock files resolve to `jose@6.1.3` and `npm ci` enforces the lock. Risk is process: stale root entries indicate the lock regeneration step was skipped, which could mask future version drift if the same pattern applies to other packages.
**Recommendation**: Regenerate all three worker lock files by running `npm install` in each worker directory after confirming the exact pin is declared in `package.json`, then commit the updated lock files. This should be done together with the wrangler exact-pin standardization to avoid multiple lock file regenerations.

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
**Description**: `langdetect 1.0.9` is the most recent PyPI release and the underlying algorithm has not been updated since 2021. No active security vulnerabilities are known. The package is used in exactly two locations (`src/evidence/metadata/language.py:28-29`) for document language detection.
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
| aiofiles | 24.1.0 | >=24.1.0,<26.0 | None known | SAFE |
| slowapi | 0.1.9 | >=0.1.9,<1.0 | None known | SAFE |
| python-magic | 0.4.27 | >=0.4.27,<1.0 | None known | SAFE |
| python-docx | 1.2.0 | >=1.1.0,<2.0 | None known | SAFE |
| pdfplumber | 0.11.9 | >=0.11.0,<1.0 | None known | SAFE |
| openpyxl | 3.1.5 | >=3.1.0,<4.0 | None known | SAFE |
| lxml | 5.4.0 | >=5.0.0,<6.0 | None known | SAFE |
| defusedxml | 0.7.1 | >=0.7.0,<1.0 | None known | SAFE |
| numpy | 2.4.2 | >=1.26.0,<3.0 | None known | SAFE |
| PyJWT[crypto] | 2.12.1 | >=2.12.0,<3.0 | CVE-2026-32597 patched in 2.12.1 | SAFE |
| bcrypt | 4.3.0 | >=4.0.0,<5.0 | None known | SAFE |
| cryptography | 46.0.5 | >=46.0.5,<48.0 | None known | SAFE |
| email-validator | 2.3.0 | >=2.0.0,<3.0 | None known | SAFE |
| pyopenssl | 26.0.0 | >=26.0.0 | CVE-2026-27448, CVE-2026-27459 floor met | SAFE |
| pyasn1 | 0.6.3 | >=0.6.3 | CVE-2026-30922 floor met | SAFE |
| langdetect | 1.0.9 | >=1.0.9,<2.0 | None known | LOW: maintenance risk |

---

## Accepted Risks (Documented)

| Advisory | Severity | Package | Decision | Review Date |
|---|---|---|---|---|
| CVE-2024-23342 | MEDIUM | ecdsa (via python-jose) | Accept — python-jose removed; ecdsa no longer in dependency graph | 2026-03-12 |
| GHSA-3x4c-7xq6-9pq8 | Moderate | next (image cache growth) | Accept — no `remotePatterns` configured; not exploitable in deployment | 2026-03-18 |
| GHSA-vpq2-c234-7xj6 | Low | @tootallnate/once | Accept — dev dependency only, no production exposure | 2026-03-12 |

---

## Docker Image Pinning Summary

| Service | Image | Pinned | Notes |
|---|---|---|---|
| postgres | pgvector/pgvector:0.8.0-pg15 | Yes | Specific version |
| neo4j | neo4j:5.27-community | Partial | Minor-only tag, no patch version (LOW finding) |
| redis | redis:7.4-alpine | Yes | Minor+patch pinned |
| cib7 | cibseven/cibseven:run-2.1.0 | Yes | Specific version |
| minio | minio/minio:RELEASE.2025-01-20T14-49-07Z | Yes | Timestamped release |
| minio-init | minio/mc:RELEASE.2025-01-20T17-06-52Z | Yes | Timestamped release (resolved since 2026-03-19) |
| mailpit | axllent/mailpit:v1.22 | Yes | Specific version |
| backend | python:3.12.11-slim | Yes | Patch-level pinned (resolved since 2026-03-19) |
| frontend | node:20.19-alpine | Yes | Patch-level pinned (resolved since 2026-03-19) |

---

## Supply Chain Risk Score: LOW-MEDIUM

The JavaScript supply chain is largely in good shape: the frontend `package-lock.json` (lockfileVersion 3) has integrity hashes for all packages; all three Cloudflare Worker lock files resolve `jose` to `6.1.3`. Two accepted npm advisories are documented and non-exploitable. Two worker-related LOW findings remain open: (1) `wrangler` uses caret ranges with inconsistent resolved versions across workers; (2) all three worker lock file root entries still show `"jose": "^6.1.3"` because the lock files were not regenerated after the `package.json` exact-pin change — no current security exposure, but a process hygiene gap.

The Python supply chain is now in good standing: `requirements.lock` was regenerated with `--generate-hashes`, providing SHA-256 tamper detection for all packages. `Dockerfile.backend` installs with `--require-hashes`, enforcing hash verification on every build. `cryptography==46.0.5`, `pyjwt==2.12.1`, `pyopenssl==26.0.0`, and `pyasn1==0.6.3` are all correctly resolved in the lock. No HIGH or MEDIUM Python dependency findings remain.

The remaining risk is the neo4j minor-only tag in `docker-compose.yml`, stale worker lock root entries for `jose`, and the long-term maintenance trajectory of `langdetect`.
