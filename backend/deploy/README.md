# Deploying the backend

Every push to `main` runs `.github/workflows/ci.yml`:

1. **Checks:** ruff, pytest, the testability audit, shellcheck, and a
   `node --check` of the WhatsApp bridge.
2. **Deploy:** only runs if every check passed. GitHub Actions SSHes to the
   Hetzner box with a key that can only run `/opt/assistant/deploy.sh`.
3. **Smoke test:** `https://assistant.alphatronex.com/healthz` must report the
   pushed commit's short SHA within 60 s.

Pull requests run the checks only. To redeploy without a commit, use Actions →
CI / CD → **Run workflow**.

**If anything fails, production stays on the previous version.** A failed
check or a missing secret means `deploy.sh` never runs. If the build fails,
the old container keeps running. The smoke test fails if the new container
doesn't come up.

## What deploy.sh does

On the server, `/opt/assistant/deploy.sh` (the source is `deploy/deploy.sh` here):

1. `git reset --hard origin/main` in `/opt/assistant/repo`.
2. Builds the image with `GIT_SHA` baked in.
3. Swaps the container with `docker compose -f backend/docker-compose.prod.yml up -d`.
4. Waits for `/healthz` on both the app (:8000) and the public demo
   (:8001, the `personal-assistant-demo` service) to report the new SHA.

The demo container gets no `.env` and no volume (see `app/demo.py`). Its
nginx site is `hetzner-infra/nginx/demo.alphatronex.com`, and CI smoke-tests
it too.

State lives outside the checkout, in `/opt/assistant/`, and the compose file
mounts it: `.env` (secrets, including the login's `ADMIN_PASSWORD_HASH` /
`SESSION_SECRET`; run `scripts/set_admin_password.py` to change the password,
replace both lines, then `docker restart personal-assistant`), `config/` (projects.yaml / channels.yaml) and
`data/` (SQLite + Google token). A deploy never touches it.

**Not deployed by this pipeline:** the WhatsApp bridge
(`/opt/whatsapp-bridge`, pm2) and its systemd units. Restarting the bridge
drops the WhatsApp session, so they're still updated by hand. See
`hetzner-infra/hetzner.md`.

**Schema changes:** `init_db()` only creates missing *tables*. A new column on
an existing table (like `youtube_channels.enabled`) must be added by hand on
the server (`ALTER TABLE ...`) before deploying code that uses it.

## One-time setup (done 2026-10)

1. Generate a deploy key on your Mac, with no passphrase:
   `ssh-keygen -t ed25519 -f ~/.ssh/deploy_personal_assistant -N "" -C "github-actions personal-assistant"`
2. Add the GitHub secret `DEPLOY_SSH_KEY` containing the **raw private key
   text**, BEGIN/END lines included, with no quotes and no base64:
   `gh secret set DEPLOY_SSH_KEY --repo alpha-tronex/Personal-Assistant < ~/.ssh/deploy_personal_assistant`
3. On the server, clone the repo and install the script:
   `git clone https://github.com/alpha-tronex/Personal-Assistant.git /opt/assistant/repo`
   `install -m 700 /opt/assistant/repo/backend/deploy/deploy.sh /opt/assistant/deploy.sh`
4. Restrict the key to that one script, in `~alphathiam/.ssh/authorized_keys`:
   `command="/opt/assistant/deploy.sh",restrict ssh-ed25519 AAAA… github-actions personal-assistant`

The first deploy replaces the old hand-started `docker run` container with the
compose-managed one; `deploy.sh` does this automatically, once.

**If you change `deploy/deploy.sh`,** re-run the `install` line in step 3.
The server runs its own copy, which a deploy doesn't update, so that a bad
push can't rewrite the deployer.

## Rollback

```bash
ssh hetzner
cd /opt/assistant/repo && git log --oneline -5      # pick the last good SHA
git reset --hard <sha> && cd backend
GIT_SHA=<sha> docker compose -f docker-compose.prod.yml up -d --build
```

The next push to `main` deploys again. To pause deploys while you
investigate, disable the workflow under Actions.
