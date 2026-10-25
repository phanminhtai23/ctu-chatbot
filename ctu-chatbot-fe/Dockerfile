FROM node:22-alpine AS build

WORKDIR /app

ARG VITE_API_BASE_URL=
ARG VITE_GOOGLE_CLIENT_ID=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_GOOGLE_CLIENT_ID=${VITE_GOOGLE_CLIENT_ID}

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:stable-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
