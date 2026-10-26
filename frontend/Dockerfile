# Build stage
FROM node:20-alpine AS build

WORKDIR /app

# Copy package files
COPY frontend/package.json frontend/package-lock.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY frontend/ ./

# Build the application
RUN npm run build

# Runtime stage
FROM nginx:1.27-alpine

# envsubst renders the nginx template at startup so the container listens on the
# platform-assigned PORT. ca-certificates lets nginx verify the backend's TLS
# certificate (Render uses a publicly trusted CA).
RUN apk add --no-cache gettext ca-certificates

# Copy built files from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy the nginx template and the startup script that substitutes the
# platform-assigned PORT and the backend target before nginx starts.
COPY frontend/nginx.conf /etc/nginx/templates/default.conf.template
COPY frontend/entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Default values keep local Docker Compose working (HTTP to backend:8000 on
# port 80). Render overrides PORT at runtime and should set BACKEND_SCHEME and
# BACKEND_TARGET to the deployed backend's public HTTPS URL.
ENV PORT=80 \
    BACKEND_SCHEME=http \
    BACKEND_TARGET=backend:8000

EXPOSE 80

# Start nginx
ENTRYPOINT ["/docker-entrypoint.sh"]