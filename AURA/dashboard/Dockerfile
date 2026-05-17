FROM node:20-alpine AS builder
WORKDIR /app
COPY dashboard/package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY dashboard/ ./
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY dashboard/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
