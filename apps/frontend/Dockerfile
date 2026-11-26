FROM node:20-alpine AS build
WORKDIR /repo

COPY package.json package-lock.json .npmrc ./
COPY apps/frontend/package.json ./apps/frontend/
COPY packages/shared-types/package.json ./packages/shared-types/

# package.json の packageManager と揃える
RUN npm install -g npm@11.19.0 && npm ci

COPY packages ./packages
COPY apps/frontend ./apps/frontend

WORKDIR /repo/apps/frontend
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY apps/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /repo/apps/frontend/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
