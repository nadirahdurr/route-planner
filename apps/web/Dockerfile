FROM node:20-alpine

WORKDIR /app

RUN npm install -g pnpm

# Copy workspace manifests first for caching
COPY package.json pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json

RUN pnpm install --filter web --no-frozen-lockfile

# Copy rest of repo
COPY . .

EXPOSE 3000

CMD ["pnpm", "--filter", "web", "dev", "--", "--hostname", "0.0.0.0"]
