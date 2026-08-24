# Production frontend: builds the React app, then serves it from Caddy along
# with TLS, Google SSO and the API proxy.
#
# Build context is the WEB DIRECTORY:
#
#     docker build --platform linux/arm64 -t interest-web web/
#
# One image rather than a separate static-server container plus a proxy: the
# Caddyfile and the assets it serves version together, so a routing change and
# the build it routes to can never be deployed out of step.

# --------------------------------------------------------------------------
FROM node:20-alpine AS build

WORKDIR /app

# Install from the lockfile first so dependency layers survive source edits.
COPY package.json package-lock.json ./
# `npm ci` refuses to run against a lockfile it cannot satisfy, which is what
# we want in a build: a silent dependency drift here would ship untested code.
RUN npm ci --include=optional

COPY . .
RUN npm run build

# --------------------------------------------------------------------------
FROM caddy:2-alpine

COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile

# Overridden at run time; the default keeps `docker run` locally honest.
ENV APP_HOSTNAME=localhost

EXPOSE 80 443

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1/ 2>/dev/null || exit 1
