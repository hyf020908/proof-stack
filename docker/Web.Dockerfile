# syntax=docker/dockerfile:1.7

FROM node:20.19.4-alpine3.21 AS builder

ENV COREPACK_HOME=/corepack
WORKDIR /workspace
RUN corepack enable && corepack prepare pnpm@10.18.3 --activate
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json ./apps/web/package.json
RUN pnpm install --frozen-lockfile
COPY apps/web ./apps/web
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN pnpm --dir apps/web build

FROM nginx:1.27.4-alpine3.21 AS runtime

COPY docker/nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /workspace/apps/web/dist /usr/share/nginx/html
RUN chown -R nginx:nginx /usr/share/nginx/html \
    && chown -R nginx:nginx /var/cache/nginx

USER nginx
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=5 \
    CMD ["wget", "--quiet", "--tries=1", "--spider", "http://127.0.0.1:8080/healthz"]
ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]
