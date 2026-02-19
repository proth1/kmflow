# KMFlow Deployment Guide

## JWT Key Management

KMFlow uses two environment variables for JWT authentication:

| Variable | Purpose | Required |
|----------|---------|----------|
| `JWT_SECRET_KEY` | Signs new tokens and verifies tokens when `JWT_SECRET_KEYS` is empty | Yes |
| `JWT_SECRET_KEYS` | Comma-separated list of keys accepted for token verification | No |

### How It Works

- **Signing**: New tokens are always signed with `JWT_SECRET_KEY`.
- **Verification**: If `JWT_SECRET_KEYS` is set, all listed keys are tried when verifying incoming tokens. If unset, only `JWT_SECRET_KEY` is used.
- **Precedence**: When `JWT_SECRET_KEYS` is set and non-empty, it fully controls the verification key list. `JWT_SECRET_KEY` is still used solely for signing.

### Key Requirements

- Minimum 32 characters of cryptographically random data
- Generate with: `python -c "import secrets; print(secrets.token_urlsafe(48))"`

### Zero-Downtime Key Rotation

This procedure rotates the JWT signing key without invalidating existing tokens.

**Step 1 -- Add new key to verification list**

```bash
# Current state: JWT_SECRET_KEY=old-key
# Add both keys so existing tokens remain valid
JWT_SECRET_KEY=old-key
JWT_SECRET_KEYS=new-key,old-key
```

Redeploy. Existing tokens (signed with `old-key`) still verify because `old-key` is in `JWT_SECRET_KEYS`.

**Step 2 -- Switch signing to new key**

```bash
JWT_SECRET_KEY=new-key
JWT_SECRET_KEYS=new-key,old-key
```

Redeploy. New tokens are now signed with `new-key`. Old tokens still verify via `old-key` in the list.

**Step 3 -- Remove old key after token expiry**

Wait for the maximum token TTL to elapse (so all tokens signed with `old-key` have expired), then remove it:

```bash
JWT_SECRET_KEY=new-key
JWT_SECRET_KEYS=
```

Redeploy. Only `new-key` is now accepted. The rotation is complete.

### Timing

Keep the old key in `JWT_SECRET_KEYS` for at least one full token TTL after switching the signing key. For example, if tokens expire after 24 hours, wait 24 hours before Step 3.
