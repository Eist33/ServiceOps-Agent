FROM node:22-bookworm-slim AS base
WORKDIR /app
RUN corepack enable
RUN apt-get update \
    && apt-get install -y --no-install-recommends libc++1 \
    && rm -rf /var/lib/apt/lists/*

FROM base AS build
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_AUTH_MODE=development
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_AUTH_MODE=$NEXT_PUBLIC_AUTH_MODE
RUN pnpm run build

FROM base AS runtime
COPY --from=build /app ./
EXPOSE 3000
CMD ["pnpm", "exec", "wrangler", "dev", "--config", "dist/server/wrangler.json", "--ip", "0.0.0.0", "--port", "3000"]
