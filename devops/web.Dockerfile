# syntax=docker/dockerfile:1
FROM node:22-slim AS build
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
ENV CONSOLE_BIND=0.0.0.0 CONSOLE_PROXY_SECRET=""
COPY --from=build /web/dist /usr/share/nginx/html
COPY devops/web.conf.template /etc/nginx/templates/default.conf.template
ENV NGINX_ENVSUBST_FILTER=CONSOLE_
EXPOSE 8080 8081
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/web-health || exit 1
