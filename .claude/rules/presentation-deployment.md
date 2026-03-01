# Presentation Deployment Rules

These rules apply whenever deploying or modifying the KMFlow presentation
at kmflow.agentic-innovations.com.

## Hard Constraints

1. **One canonical file**: `docs/presentations/index.html` is the SOLE
   presentation HTML. Never create, copy, or maintain a second `.html`
   file in this directory. Cloudflare Pages serves `index.html` at `/`
   automatically.

2. **No hardcoded filename redirects in the Worker**: The worker at
   `infrastructure/cloudflare-workers/presentation-auth/src/index.ts`
   must NEVER redirect `/` to a named `.html` file. This caused a
   production incident on 2026-02-17 where users were silently served
   stale content. Let Pages handle the default document.

3. **Verify after every deploy**: After deploying to Pages, curl the
   deployment preview URL and verify: (a) response size matches local
   `index.html`, (b) content contains expected markers (e.g.,
   `grep -c diagram-container`). Do NOT skip this step.

## Deployment Sequence

1. Deploy Pages: `npx wrangler pages deploy docs/presentations/ --project-name kmflow-presentation`
2. Deploy Worker (if changed): `cd infrastructure/cloudflare-workers/presentation-auth && env -u CLOUDFLARE_API_TOKEN npx wrangler deploy`
3. Purge cache: POST to `/zones/{zone_id}/purge_cache` with `purge_everything: true`
4. Verify preview URL content matches local file

### Content-Only vs Worker Deploys

4. **Pages-only for content changes**: When only presentation HTML/CSS/JS
   changes, deploy Pages only (step 1). Do NOT redeploy the worker. A worker
   redeploy can invalidate user sessions (cold-start re-fetches Descope JWKS,
   can fail JWT validation on first request), forcing users to re-authenticate.

5. **Worker deploy only when worker code/config changes**: Only run step 2
   when `src/index.ts`, `wrangler.toml`, or secrets actually changed. This
   applies to ALL presentation workers (kmflow, state-street-apex, etc.).

This rule exists because a worker redeploy resets the Cloudflare isolate,
which re-initializes the JWKS keyset fetcher. During that cold-start window,
in-flight JWT validations can fail and bounce authenticated users to login.

## Failure Mode Checklist

When deployed content doesn't match local:
- [ ] Check worker source for hardcoded redirects (`grep -n '\.html' src/index.ts`)
- [ ] Check Pages preview URL returns correct file size
- [ ] Check service token secrets are valid (CF_ACCESS_CLIENT_ID/SECRET)
- [ ] Purge zone cache for agentic-innovations.com
- [ ] Tell user to hard-refresh browser (Cmd+Shift+R)

## Architecture Reference

### KMFlow Presentation
- Canonical file: `docs/presentations/index.html`
- Pages project: `kmflow-presentation` -> `kmflow-presentation.pages.dev`
- Worker: `infrastructure/cloudflare-workers/presentation-auth/`
- Custom domain: `kmflow.agentic-innovations.com`
- Service token: `kmflow-presentation-worker-bypass`

### State Street APEX Presentation
- Canonical file: `docs/presentations/state-street-apex/index.html`
- Pages project: `kmflow-state-street-apex` -> `kmflow-state-street-apex.pages.dev`
- Worker: `infrastructure/cloudflare-workers/state-street-apex-auth/`
- Custom domain: `state-street-apex.agentic-innovations.com`
- Service token: `state-street-apex-worker-bypass`

### Shared
- Descope project ID: `P39ERvEl6A8ec0DKtrKBvzM4Ue5V` (shared across all presentations)
- CF Access: blocks direct `.pages.dev` access on all presentation projects
- Zone: `agentic-innovations.com` (`c8c493cfbb6a3e175c3b135abf4e7e56`)
