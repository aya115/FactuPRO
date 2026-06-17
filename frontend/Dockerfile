# syntax=docker/dockerfile:1
FROM node:20-alpine AS build

WORKDIR /app

# Réduit fortement le temps de `react-scripts build` (surtout sous Docker Desktop / Windows).
ENV GENERATE_SOURCEMAP=false
ENV DISABLE_ESLINT_PLUGIN=true
ENV SKIP_PREFLIGHT_CHECK=true
# Évite le ralentissement / swap quand Webpack + Terser consomment beaucoup de RAM dans le conteneur
ENV NODE_OPTIONS=--max-old-space-size=4096

COPY package.json package-lock.json .npmrc ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --fund=false

COPY . .

ARG REACT_APP_API_BASE=http://localhost:5000
ENV REACT_APP_API_BASE=$REACT_APP_API_BASE

RUN npm run build

FROM nginx:alpine

COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
