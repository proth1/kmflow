FROM node:20-alpine AS base

WORKDIR /app

# Accept build-time API URL
ARG NEXT_PUBLIC_API_URL=http://localhost:8002
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

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
