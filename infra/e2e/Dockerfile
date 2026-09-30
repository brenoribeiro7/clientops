ARG NODE_IMAGE=node:24.21.0-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6
ARG PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright:v1.63.0-noble@sha256:eff16c30e6f3f4af0a03fa4b706120d5e9b0891c344a27d64559aff5900a4a27

FROM ${NODE_IMAGE} AS node-runtime
FROM ${PLAYWRIGHT_IMAGE}
COPY --from=node-runtime /usr/local/ /usr/local/
WORKDIR /work/frontend
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
COPY e2e/ ../e2e/
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    NODE_PATH=/work/frontend/node_modules
ENTRYPOINT []
CMD ["npm", "run", "test:e2e"]
