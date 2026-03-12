# Accepted Security Risks

Last reviewed: 2026-03-12

## Python Dependencies

### CVE-2024-23342 — ecdsa (0.19.1)

- **Severity**: MEDIUM
- **Package**: ecdsa 0.19.1 (transitive, via python-jose)
- **Description**: Timing side-channel in ECDSA signature verification
- **Fix available**: No fix version published
- **Justification**: KMFlow uses PyJWT with `cryptography` backend for all JWT operations. The `ecdsa` pure-Python library is installed as a transitive dependency of `python-jose` but is not used for any cryptographic operations in KMFlow. PyJWT's `cryptography` backend uses OpenSSL's constant-time ECDSA implementation. The vulnerability requires a local attacker with precise timing measurement capability. Risk is negligible.
- **Mitigation**: Monitor for a fix release. Consider replacing `python-jose` with `PyJWT` if `python-jose` is no longer needed.
- **Review date**: 2026-03-12

## Frontend Dependencies (npm)

### GHSA-vpq2-c234-7xj6 — @tootallnate/once (<3.0.1)

- **Severity**: LOW (4 findings)
- **Package**: @tootallnate/once (transitive, via jest-environment-jsdom → jsdom → http-proxy-agent)
- **Description**: Incorrect control flow scoping
- **Fix available**: Requires breaking change to jest-environment-jsdom@27 (from 30.x)
- **Justification**: Dev-only test dependency. Not present in production `next build` output. The vulnerability is in a test HTTP proxy agent used by jsdom for DOM simulation during Jest tests. No production exposure.
- **Mitigation**: Will be resolved when jest-environment-jsdom releases a non-breaking fix. Monitor upstream.
- **Review date**: 2026-03-12
