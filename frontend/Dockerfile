FROM node:20-alpine AS base

WORKDIR /app

# Backend API URL (used by Next.js rewrites proxy, not exposed to client)
ARG API_URL=http://localhost:8000
ENV API_URL=$API_URL

# Install dependencies
COPY package.json package-lock.json* ./
RUN npm ci 2>/dev/null || npm install

# Copy source
COPY . .

# Build (disabled for dev mode)
# RUN npm run build

EXPOSE 3000

# Development mode
CMD ["npm", "run", "dev"]
