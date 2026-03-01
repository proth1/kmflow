# Frontend Docker Build Rules

## Production Build by Default

The frontend Docker container MUST run a production build (`next build` + `node server.js`), never `npm run dev`, for all environments accessible over the network (including dev tunnels).

### Why

Running Next.js dev server over Cloudflare Tunnel caused the Knowledge Graph page to hang indefinitely — unminified, uncompressed chunks (~1MB for cytoscape) were too slow through the Worker → Tunnel → Docker roundtrip. Switching to a production build fixed load times from "forever" to sub-second.

### Dockerfile Structure

The Dockerfile uses multi-stage builds with named targets:

- **`runner`** (default) — `next build` + standalone output + `node server.js`. Pre-built, minified, tree-shaken, compressed.
- **`dev`** — `npm run dev` with hot reload. Only for local development with volume mounts.

### docker-compose Usage

```bash
# Production (default) — used by tunnel, CI, staging
docker compose up frontend

# Development (local only) — hot reload with volume mounts
docker compose --profile dev up frontend-dev
```

### Rules

1. **Never run `npm run dev` in a container accessible via tunnel or public URL.** Dev server generates chunks on-the-fly without minification or compression.
2. **Remove source volume mounts from the production service.** Volume mounts (`./frontend/src:/app/src`) bypass the built output and force dev-mode behavior.
3. **Heavy visualization libraries (cytoscape, bpmn-js, recharts) must use `next/dynamic` with `ssr: false`** to keep them in separate lazy-loaded chunks.
4. **All `next build` errors must be fixed before merging.** The production Dockerfile will catch issues that dev mode silently ignores:
   - Named exports from page files (Next.js 15 only allows `default` + metadata exports)
   - Missing Suspense boundaries around `useSearchParams()`
   - Type errors that dev mode defers
5. **After rebuilding, verify health** before considering the deploy complete:
   ```bash
   docker compose build frontend
   docker compose up -d frontend
   curl -s -o /dev/null -w "%{http_code}" http://localhost:3002/
   ```
