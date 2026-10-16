# Stage 1: build the React app into plain HTML, CSS and JavaScript files (in /app/dist)
FROM node:24-alpine AS build
WORKDIR /app
# Install the exact package versions in package-lock.json. Copied first so Docker can reuse this
# step when only the code changes.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY index.html vite.config.js ./
COPY src ./src
RUN npm run build

# Stage 2: a small Nginx image that just serves those files. Node isn't in the final image.
FROM nginx:1.30-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
