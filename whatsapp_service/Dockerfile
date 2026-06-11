FROM node:20-slim

WORKDIR /app

# git is required by Baileys sub-dependencies; rewrite SSH GitHub URLs to HTTPS
# so the Docker build doesn't need SSH keys
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* \
    && git config --global url."https://github.com/".insteadOf "ssh://git@github.com/" \
    && git config --global url."https://github.com/".insteadOf "git@github.com:"

# Install dependencies first (layer cache)
COPY package.json ./
RUN npm install --omit=dev

# Copy bridge code
COPY index.js ./

# Auth directory — mount as volume to persist session across restarts
RUN mkdir -p /app/auth
VOLUME ["/app/auth"]

EXPOSE 3000

CMD ["node", "index.js"]
