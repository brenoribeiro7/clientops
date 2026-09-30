ARG NODE_IMAGE=node:24.21.0-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6
ARG NGINX_IMAGE=nginx:1.28.0-alpine-slim@sha256:ce2bd4775ed6859d35f47d65401ee9f35f1dd00b32ed05f0ce38b68aa1830195

FROM ${NODE_IMAGE} AS builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ${NGINX_IMAGE} AS runtime
RUN rm -f /etc/nginx/conf.d/default.conf \
    && mkdir -p /var/cache/nginx/client_temp /var/cache/nginx/proxy_temp \
    && chown -R 101:101 /var/cache/nginx
COPY --chown=101:101 infra/nginx/nginx.conf /etc/nginx/nginx.conf
COPY --chown=101:101 infra/nginx/server-http.conf /etc/nginx/conf.d/server.conf
COPY --chown=101:101 infra/nginx/headers-common.conf /etc/nginx/snippets/headers-common.conf
COPY --chown=101:101 infra/nginx/headers-public.conf /etc/nginx/snippets/headers-public.conf
COPY --chown=101:101 infra/nginx/headers-private.conf /etc/nginx/snippets/headers-private.conf
COPY --chown=101:101 infra/nginx/routes.conf /etc/nginx/snippets/routes.conf
COPY --from=builder --chown=101:101 /app/dist /usr/share/nginx/html
USER 101:101
EXPOSE 8080 8443
ENTRYPOINT []
CMD ["nginx", "-g", "daemon off;"]
