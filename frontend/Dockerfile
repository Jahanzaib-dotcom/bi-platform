# ============================================================
# Stage 1: deps — install all node_modules
# ============================================================
FROM node:20-alpine AS deps

RUN apk add --no-cache libc6-compat

WORKDIR /app

# Copy package manifests and install dependencies
COPY package.json package-lock.json* yarn.lock* pnpm-lock.yaml* ./

RUN \
  if [ -f yarn.lock ]; then \
    yarn install --frozen-lockfile; \
  elif [ -f package-lock.json ]; then \
    npm ci; \
  elif [ -f pnpm-lock.yaml ]; then \
    corepack enable pnpm && pnpm install --frozen-lockfile; \
  else \
    npm install; \
  fi

# ============================================================
# Stage 2: builder — build the Next.js application
# ============================================================
FROM node:20-alpine AS builder

WORKDIR /app

# Build-time environment variables injected at image build time
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WS_URL

ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL} \
    NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL} \
    NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN \
  if [ -f yarn.lock ]; then \
    yarn build; \
  elif [ -f package-lock.json ]; then \
    npm run build; \
  elif [ -f pnpm-lock.yaml ]; then \
    corepack enable pnpm && pnpm run build; \
  else \
    npm run build; \
  fi

# ============================================================
# Stage 3: runner — minimal production image
# ============================================================
FROM node:20-alpine AS runner

RUN apk add --no-cache dumb-init

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Create non-root user
RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

# Copy only what Next.js standalone output needs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

# Use dumb-init to handle PID 1 signal forwarding
ENTRYPOINT ["dumb-init", "--"]
CMD ["node", "server.js"]
