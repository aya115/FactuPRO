FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json .npmrc ./
RUN npm ci

COPY . .

ARG REACT_APP_API_BASE=http://localhost:5000
ENV REACT_APP_API_BASE=$REACT_APP_API_BASE

RUN npm run build

FROM nginx:alpine

COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
