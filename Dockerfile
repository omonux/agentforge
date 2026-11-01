# Build the React dashboard.
FROM node:20-alpine AS frontend
WORKDIR /build
COPY apps/web/package*.json ./
RUN npm install
COPY apps/web/ ./
RUN npm run build

# Run the API and serve the dashboard behind one same-origin reverse proxy.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATABASE_PATH=/data/agentforge.db COOKIE_SECURE=true PORT=10000
WORKDIR /srv/agentforge
RUN apt-get update && apt-get install -y --no-install-recommends nginx supervisor ffmpeg && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=frontend /build/dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/supervisord.conf /etc/supervisor/conf.d/agentforge.conf
RUN mkdir -p /data && chown -R www-data:www-data /usr/share/nginx/html
EXPOSE 10000
CMD ["supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]
