# D3: Dependency & Regression Audit Findings

**Auditor**: D3 (Dependency Auditor)
**Date**: 2026-02-20
**Scope**: CVEs in dependencies, lock file status, abandoned packages, PR #127 regression risks

---

## Summary

| Category | Count |
|---|---|
| CRITICAL findings | 0 |
| HIGH findings | 1 |
| MEDIUM findings | 4 |
| LOW findings | 3 |
| SAFE/INFO | 3 |

**Python dependency count (production)**: 24 packages (in `[project.dependencies]`)
**Python lock file status**: NONE — no `poetry.lock`, `Pipfile.lock`, or pinned `requirements.txt`
**Node.js direct dependency count**: 34 (20 production, 14 dev)
**Node.js transitive package count**: 613 (from `frontend/package-lock.json`)
**Node.js lock file status**: PRESENT — `frontend/package-lock.json` (lockfileVersion 3)

**CVE Scan Results**:
- `pip-audit` against production Python deps: **0 known vulnerabilities found**
- `npm audit` against frontend deps: **0 vulnerabilities found**

---

## Findings

### [HIGH] DEPENDENCY-MANAGEMENT: No Python Lock File

**File**: `pyproject.toml` (project root)
**Agent**: D3 (Dependency Auditor)
**Evidence**:
```
# No poetry.lock, Pipfile.lock, or requirements.txt found anywhere
# Only pyproject.toml with range-based versions:
"fastapi>=0.115.0,<1.0",
"sqlalchemy[asyncio]>=2.0.36,<3.0",
"pydantic>=2.10.0,<3.0",
```
**Description**: No Python lock file exists. All production dependencies use range-based version specifiers (`>=x.y,<x+1.0`). This means `pip install -e .` will resolve different package versions across environments and deployment times. The frontend correctly uses `package-lock.json` (lockfileVersion 3) but the Python side has no equivalent.
**Risk**: Non-deterministic builds. A security patch or breaking release within a declared range can silently change the installed version between developer machines, CI, and production. For a security-sensitive platform (JWT, encryption, LLM calls), this is a significant supply-chain risk.
**Recommendation**: Adopt `poetry` with a committed `poetry.lock`, or generate a pinned `requirements.txt` via `pip freeze > requirements.txt` and commit it. The pipeline-orchestrator should install from the lock file.

---

### [MEDIUM] VERSION-PINNING: Frontend Deps Use Caret Ranges (No Exact Pinning)

**File**: `frontend/package.json:19-38`
**Agent**: D3 (Dependency Auditor)
**Evidence**:
```json
"next": "^15.5.10",
"react": "^18.3.0",
"bpmn-js": "^18.12.0",
"@tailwindcss/postcss": "^4.1.18",
"cytoscape": "^3.33.1"
```
**Description**: All frontend production and dev dependencies use the `^` (caret) operator, which permits any non-breaking minor/patch version. While `package-lock.json` pins the installed versions in the lock file, `npm install` on a fresh checkout will accept any compatible version, making lock file discipline essential. A corrupted or missing lock file would lead to non-deterministic installs.
**Risk**: Medium. The lock file is present and correct, but the lack of exact pinning in `package.json` means lock file drift is possible across environments. `next@^15.5.10` would accept `15.99.x` without a version floor.
**Recommendation**: Consider using exact versions in `package.json` (remove the `^`) for production dependencies, relying on the lock file for transitive pinning. Alternatively, document that `npm ci` (not `npm install`) must always be used to enforce lock file adherence.

---

### [MEDIUM] DEPENDENCY-CATEGORIZATION: Build-time Packages in Production Dependencies

**File**: `frontend/package.json:24,32,37,38`
**Agent**: D3 (Dependency Auditor)
**Evidence**:
```json
"dependencies": {
  "@tailwindcss/postcss": "^4.1.18",
  "postcss": "^8.5.6",
  "tailwindcss": "^4.1.18",
  "tailwindcss-animate": "^1.0.7"
}
```
**Description**: `tailwindcss`, `@tailwindcss/postcss`, `postcss`, and `tailwindcss-animate` are CSS build-time tools. In a Next.js project using Tailwind CSS, these are processed at compile time and do not need to be runtime dependencies. They should be in `devDependencies`. The same applies to `autoprefixer`, which is already correctly placed in `devDependencies`.
**Risk**: Low-medium. Inflates production `node_modules` bundle size. In containerized deployments using `npm ci --omit=dev`, these would be excluded, but misclassification creates confusion and risks `npm audit` scope errors.
**Recommendation**: Move `tailwindcss`, `@tailwindcss/postcss`, `postcss`, and `tailwindcss-animate` to `devDependencies`.

---

### [MEDIUM] DEPENDENCY-SCOPE: `cryptography` Package Used But Not Declared

**File**: `src/core/encryption.py:15`, `pyproject.toml`
**Agent**: D3 (Dependency Auditor)
**Evidence**:
```python
# src/core/encryption.py:15
from cryptography.fernet import Fernet, InvalidToken
```
```toml
# pyproject.toml - cryptography is NOT listed in [project.dependencies]
# PyJWT[crypto] is listed, which installs cryptography as a transitive dep
"PyJWT[crypto]>=2.9.0,<3.0",
```
**Description**: `encryption.py` directly imports from `cryptography.fernet`, but `cryptography` is not listed as an explicit production dependency. It is installed transitively via `PyJWT[crypto]`. This is an undeclared direct dependency — if `PyJWT` ever drops its `[crypto]` extra or the extras API changes, `encryption.py` will fail at runtime with no warning at install time.
**Risk**: Medium. Runtime breakage risk if PyJWT dependency tree changes. Security-critical code (Fernet encryption for credentials, API keys) depends on a transitive dependency.
**Recommendation**: Add `cryptography>=42.0.0,<44.0` explicitly to `[project.dependencies]` in `pyproject.toml`.

---

### [MEDIUM] PR-127-REGRESSION: Raw HTTP Call Bypasses Anthropic SDK in suggester.py

**File**: `src/simulation/suggester.py:128-144`
**Agent**: D3 (Dependency Auditor)
**Evidence**:
```python
# src/simulation/suggester.py - raw HTTP call, no SDK
async with httpx.AsyncClient(timeout=15.0) as client:
    response = await client.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",  # ← hardcoded to 2023-06-01
            "content-type": "application/json",
        },
        json={"model": "claude-sonnet-4-20250514", ...},  # ← different model than config
    )
# vs. src/rag/copilot.py - uses Anthropic SDK properly
client = anthropic.AsyncAnthropic()
```
**Description**: PR #127 introduced `AlternativeSuggesterService` which makes raw `httpx` calls to the Anthropic API instead of using the `anthropic` SDK (which is available as the `ai` optional extra). Two specific issues:
1. The `anthropic-version` header is hardcoded to `2023-06-01` — this is the API version string, not well-maintained going forward.
2. The model is hardcoded to `claude-sonnet-4-20250514`, while `src/core/config.py:70` defines `copilot_model: str = "claude-sonnet-4-5-20250929"` — two different model versions in the same codebase with no shared config.

The `anthropic` SDK (`anthropic>=0.40.0`) is declared in `pyproject.toml` under the `[ai]` optional extra — it is already available and used correctly in `rag/copilot.py`. `suggester.py` should use the same SDK.
**Risk**: Medium-high regression. Hardcoded model names and API versions in a newly-introduced service create drift risk. If the API version is deprecated by Anthropic, or if the model ID changes, `suggester.py` will silently fail while `copilot.py` (which uses the SDK) would be more resilient.
**Recommendation**: Refactor `AlternativeSuggesterService._call_llm()` to use the `anthropic.AsyncAnthropic` SDK (matching `copilot.py`). Use `settings.copilot_model` from `src/core/config.py` rather than a hardcoded model string.

---

### [LOW] SUPPLY-CHAIN: GitHub Actions CI Removed, No Automated Dependency Scanning Gate

**File**: `.github/workflows/ci.yml` (deleted in PR #127), `.claude/agents/pipeline-orchestrator.md`
**Agent**: D3 (Dependency Auditor)
**Evidence**:
```yaml
# Deleted in PR #127 — previously included:
- name: Python dependency audit
  run: pip freeze | ... && pip-audit --strict --desc -r /tmp/audit-reqs.txt
- name: Frontend dependency audit
  run: npm audit --audit-level=high
```
**Description**: PR #127 deleted the GitHub Actions CI workflow and replaced it with a Claude Code `pipeline-orchestrator.md` agent. The pipeline-orchestrator does include security scan steps (`pip-audit` + `npm audit` in Step 6), but these steps are only executed when a human manually invokes `/pipeline`. There is no automated trigger on PR creation or push to main. This creates a gap where dependency vulnerabilities could be introduced without automated detection.
**Risk**: Low-medium. Current CVE scan shows 0 vulnerabilities, but the enforcement mechanism is now manual-only.
**Recommendation**: Either restore a minimal GitHub Actions workflow for dependency scanning (separate from the pipeline-orchestrator), or document that `/pipeline` must be run before every merge to main. The `.claude/hooks/prevent-traditional-pipelines.js` hook actively prevents recreating GitHub Actions workflows, which should be re-evaluated for at least the security scan step.

---

### [LOW] DEPENDENCY-QUALITY: `minimatch` Override Suggests Historical Vulnerability

**File**: `frontend/package.json:40-42`
**Agent**: D3 (Dependency Auditor)
**Evidence**:
```json
"overrides": {
  "minimatch": "^10.2.1"
}
```
**Description**: The `overrides` block pins `minimatch` to `^10.2.1`, which is a known remediation pattern for CVE-2022-3517 (ReDoS in minimatch). While `npm audit` currently shows 0 vulnerabilities (meaning the override is working correctly), the presence of this override indicates that transitive dependencies still pull in older `minimatch` versions that would be vulnerable without the override.
**Risk**: Low. The override is functioning correctly. However, it must be maintained as a transitive dependency list changes.
**Recommendation**: Document why the override exists (CVE-2022-3517). Periodically review whether the transitive dependency that required `minimatch` has been updated to use a fixed version, at which point the override can be removed.

---

### [LOW] DEPENDENCY-MAINTENANCE: `aiofiles` Version Cap Too Tight

**File**: `pyproject.toml:36`
**Agent**: D3 (Dependency Auditor)
**Evidence**:
```toml
"aiofiles>=24.1.0,<25.0",
```
**Description**: `aiofiles` is capped to `<25.0`. The `24.x` release was from mid-2024. As of early 2026, this cap may prevent receiving security patches if `aiofiles` releases a `25.x` series. All other dependencies correctly use `<(major+1).0` caps which allow minor/patch updates within the major version — this one is consistent in pattern but the version number `<25.0` looks like it could be a mistake (perhaps `<2.0` was intended, as earlier aiofiles versions were `0.x`).
**Risk**: Low. Functional concern rather than an active vulnerability, but worth reviewing.
**Recommendation**: Verify intended version range for `aiofiles`. If the package follows semantic versioning at major versions, `<25.0` may be correct. If the actual release series is `24.x` (not `240.x`), check whether future versions would be blocked by this cap.

---

## Python Dependency Health Summary

| Package | Declared Version | Usage Verified | Status |
|---|---|---|---|
| fastapi | >=0.115.0,<1.0 | Yes | SAFE |
| uvicorn[standard] | >=0.32.0,<1.0 | Yes | SAFE |
| sqlalchemy[asyncio] | >=2.0.36,<3.0 | Yes | SAFE |
| asyncpg | >=0.30.0,<1.0 | Yes | SAFE |
| alembic | >=1.14.0,<2.0 | Yes | SAFE |
| pgvector | >=0.3.6,<1.0 | Yes | SAFE |
| neo4j | >=5.27.0,<6.0 | Yes | SAFE |
| redis[hiredis] | >=5.2.0,<6.0 | Yes | SAFE |
| pydantic | >=2.10.0,<3.0 | Yes | SAFE |
| pydantic-settings | >=2.7.0,<3.0 | Yes | SAFE |
| pyyaml | >=6.0,<7.0 | Yes | SAFE |
| python-dotenv | >=1.0.1,<2.0 | Yes | SAFE |
| httpx | >=0.28.0,<1.0 | Yes | SAFE |
| python-multipart | >=0.0.22,<1.0 | Yes (bumped in PR #127) | SAFE |
| aiofiles | >=24.1.0,<25.0 | Yes | LOW (version cap review) |
| slowapi | >=0.1.9,<1.0 | Yes | SAFE |
| python-magic | >=0.4.27,<1.0 | Yes (lazy import) | SAFE |
| python-docx | >=1.1.0,<2.0 | Yes (lazy import) | SAFE |
| pdfplumber | >=0.11.0,<1.0 | Yes (lazy import) | SAFE |
| openpyxl | >=3.1.0,<4.0 | Yes (lazy import) | SAFE |
| lxml | >=5.0.0,<6.0 | Yes | SAFE |
| defusedxml | >=0.7.0,<1.0 | Yes | SAFE |
| numpy | >=1.26.0,<3.0 | Yes | SAFE |
| PyJWT[crypto] | >=2.9.0,<3.0 | Yes | SAFE |
| bcrypt | >=4.0.0,<5.0 | Yes | SAFE |
| email-validator | >=2.0.0,<3.0 | Yes | SAFE |
| cryptography | NOT DECLARED | Yes (direct import) | MEDIUM (undeclared) |

### Optional Extras (Not in Production Requirements)
| Extra | Package | Usage |
|---|---|---|
| [ml] | scikit-learn | Not found in current imports (future use) |
| [pdf] | weasyprint | Used in `src/core/pdf_generator.py` (lazy import) |
| [datalake] | deltalake, pyarrow | Not found in current imports (future use) |
| [ai] | anthropic>=0.40.0 | Used in `src/rag/copilot.py` but NOT in `src/simulation/suggester.py` |
| [databricks] | databricks-sdk | Not found in current imports (future use) |

---

## PR #127 Regression Risk Assessment

| Change | Regression Risk | Notes |
|---|---|---|
| python-multipart bumped 0.0.18→0.0.22 | LOW | Patch version bump, security fix |
| 3 type stubs added to dev deps | NONE | Dev-only, no runtime impact |
| 9 mypy ignore_missing_imports entries added | LOW | Documentation of existing optional imports |
| New files: epistemic.py, financial.py, ranking.py, suggester.py | MEDIUM | All new code, test coverage added |
| `suggester.py` uses raw httpx vs. Anthropic SDK | MEDIUM | Inconsistent with copilot.py, hardcoded model/API versions |
| GitHub Actions CI deleted | MEDIUM | Automated security gates replaced with manual pipeline |
| `src/api/routes/simulations.py` expanded +665 lines | LOW-MEDIUM | High addition rate; tests exist (1468 passed) |

---

## Supply Chain Risk Score: MEDIUM

No active CVEs detected. Primary risks are operational (no lock file, CI removed) and regression-quality (inconsistent LLM API usage introduced in PR #127). No abandoned, malicious, or typosquatted packages detected.
