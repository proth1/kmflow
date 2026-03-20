FROM node:20-alpine AS base

WORKDIR /app

# Backend API URL (used by Next.js rewrites proxy, not exposed to client)
ARG API_URL=http://localhost:8000
ENV API_URL=$API_URL

# ── Dependencies ─────────────────────────────────────────────
FROM base AS deps
COPY package.json package-lock.json* ./
RUN npm ci

# ── Production build ─────────────────────────────────────────
FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# ── Production runner ────────────────────────────────────────
FROM base AS runner
ENV NODE_ENV=production

# Next.js standalone output copies only what's needed
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

CMD ["node", "server.js"]

# ── Development mode ─────────────────────────────────────────
FROM base AS dev
COPY --from=deps /app/node_modules ./node_modules
COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev"]
