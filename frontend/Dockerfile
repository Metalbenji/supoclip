# Use Bun as the base image
FROM oven/bun:1.2-debian AS base

# Install Node.js 22.x for tooling that requires modern Node (e.g. Prisma 7, Next 16)
ARG NODE_VERSION=22.13.1
RUN apt-get update && apt-get install -y curl ca-certificates xz-utils \
    && curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" -o /tmp/node.tar.xz \
    && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
    && rm -f /tmp/node.tar.xz \
    && rm -rf /var/lib/apt/lists/* \
    && node -v && npm -v && bun -v

# Dependencies stage
FROM base AS deps
WORKDIR /app

# Copy package.json and lockfile
COPY package.json bun.lock ./
RUN bun install

# Development stage
FROM base AS development
WORKDIR /app

# Install OpenSSL (required for Prisma) and curl for healthchecks
RUN apt-get update && apt-get install -y openssl curl && rm -rf /var/lib/apt/lists/*

# Copy dependencies from deps stage
COPY --from=deps /app/node_modules ./node_modules
COPY package.json bun.lock ./

# Copy application code (will be overridden by volume mounts in dev)
COPY . .

# Generate Prisma client
RUN bunx prisma generate

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
ENV NEXT_TELEMETRY_DISABLED=1

# Start development server with hot-reload
CMD ["bun", "run", "dev"]

# Builder stage (for production)
FROM base AS builder
WORKDIR /app

# Install OpenSSL (required for Prisma)
RUN apt-get update && apt-get install -y openssl && rm -rf /var/lib/apt/lists/*

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Generate Prisma client before building
RUN bunx prisma generate

# Build the Next.js app
ENV NEXT_TELEMETRY_DISABLED=1
# Skip linting during build (generated Prisma code has lint warnings)
ENV SKIP_LINT=1
# Next 16.2.x uses worker_threads options Bun does not fully implement yet.
RUN npm run build

# Runner stage (for production)
FROM base AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Install OpenSSL (required for Prisma) and curl for healthchecks
RUN apt-get update && apt-get install -y openssl curl && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# Copy the built application
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Copy Prisma generated client and schema
COPY --from=builder --chown=nextjs:nodejs /app/src/generated/prisma ./src/generated/prisma
COPY --from=builder /app/prisma ./prisma

USER nextjs

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Start the application
CMD ["bun", "server.js"]
