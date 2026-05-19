# Examples

## Which Example To Use

| Path | Use Case | Persistent Data Location |
|---|---|---|
| `docker-compose.pip.yml` | Fresh local smoke test from Git plugin install | Docker named volumes only |
| `docker-compose.production-vps.yml` | Public VPS deployment with HTTPS through Traefik | Host bind mounts under `/srv/hermes` by default |
| `mac-mini/` | Zip-friendly Mac mini deployment bundle for local or LAN access | Host bind mounts under `/Users/Shared/hermes` by default |

For production, back up the host bind-mounted directories. The named volumes in these examples are runtime internals that can be recreated.

## Fresh Docker Git Install

`docker-compose.pip.yml` starts a clean Hermes Agent and WebUI stack that installs `hermes-wiki` from the GitHub repository with `hermes plugins install --enable`.

The example installs the repo root as the Hermes directory plugin, then runs `hermes wiki deps --install all` in the Agent runtime. WebUI dependencies are installed from the cloned plugin root `requirements.txt` if WebUI imports plugin code directly.

It intentionally does not reuse the repo-local `docker/` directory, existing profiles, auth files, workspaces, or bind-mounted plugin source.

Start it:

```bash
docker compose -f examples/docker-compose.pip.yml up -d
```

Open Hermes WebUI:

```text
http://127.0.0.1:8787
```

Override the repository URL:

```bash
HERMES_WIKI_REPO='https://github.com/zombiearnie88/hermes-wiki.git' \
  docker compose -f examples/docker-compose.pip.yml up -d
```

Use a local port other than `8787`:

```bash
HERMES_WEBUI_PORT=8877 docker compose -f examples/docker-compose.pip.yml up -d
```

Verify plugin state in the Hermes Agent runtime:

```bash
docker compose -f examples/docker-compose.pip.yml exec hermes-agent \
  /opt/hermes/.venv/bin/hermes plugins list
```

Verify WebUI runtime dependencies:

```bash
docker compose -f examples/docker-compose.pip.yml exec -u 0 hermes-webui \
  /app/venv/bin/python3 -c "import json_repair, fitz, markitdown"
```

Reset all example state:

```bash
docker compose -f examples/docker-compose.pip.yml down -v
```

This removes the named volumes used by the example, including Hermes home, WebUI venv, and workspace state.

## Production VPS

`docker-compose.production-vps.yml` is intended for a public VPS with DNS pointing at the server. It exposes only Traefik on ports `80` and `443`; service ports such as the Hermes API port `8642` remain internal to Docker and are reached publicly through HTTPS routes.

Public routes:

| URL | Target |
|---|---|
| `https://ai.rubiklab.vip` | Hermes WebUI |
| `https://panel.rubiklab.vip` | Hermes Agent dashboard |
| `https://chat.rubiklab.vip` | Open WebUI |
| `https://openai.rubiklab.vip` | Hermes Agent OpenAI-compatible API |

Create persistent host directories:

```bash
sudo mkdir -p /srv/hermes/home /srv/hermes/workspace /srv/hermes/open-webui
sudo chown -R 1000:1000 /srv/hermes
```

Set deployment variables:

```bash
export ACME_EMAIL=admin@example.com
export HERMES_API_SERVER_KEY='replace-with-random-secret'
export HERMES_WEBUI_PASSWORD='replace-with-random-password'
export HERMES_DASHBOARD_BASIC_AUTH='admin:$apr1$4jLM/vx0$b4q14IjUlu4WBch8qkQz2/'
export OPEN_WEBUI_SECRET_KEY='replace-with-random-secret'
export OPEN_WEBUI_ADMIN_EMAIL='admin@rubiklab.vip'
export OPEN_WEBUI_ADMIN_PASSWORD='replace-with-random-password'
```

`examples/env.vps.example` includes a generated dashboard BasicAuth password. If you put an APR1 hash in a Compose env file, keep dollar signs doubled as `$$` so Compose does not interpolate them.

Generate random secrets with `openssl rand -hex 32`.

Ensure DNS for `ai.rubiklab.vip`, `panel.rubiklab.vip`, `chat.rubiklab.vip`, and `openai.rubiklab.vip` points at the VPS before starting the stack.

Start it:

```bash
docker compose -f examples/docker-compose.production-vps.yml up -d
```

Validate the public WebUI and dashboard routes:

```bash
curl -I https://ai.rubiklab.vip
curl -I https://panel.rubiklab.vip
curl -I https://chat.rubiklab.vip
curl -fsS https://openai.rubiklab.vip/health
curl -fsS -H 'Authorization: Bearer <HERMES_API_SERVER_KEY>' https://openai.rubiklab.vip/v1/models
```

Open WebUI connects to Hermes Agent through `http://hermes-agent:8642/v1` on the internal Docker network. External OpenAI-compatible clients should use `https://openai.rubiklab.vip/v1` through Traefik; do not publish the raw Hermes API port `8642` publicly.

ONLYOFFICE Desktop OpenAI-compatible settings:

| Setting | Value |
|---|---|
| Base URL | `https://openai.rubiklab.vip/v1` |
| API key | `HERMES_API_SERVER_KEY` |
| Model | `hermes-agent` |

Open WebUI uses `ghcr.io/open-webui/open-webui:main-slim` by default. The slim image may download RAG, speech-to-text, tokenizer, or related cache assets into `/srv/hermes/open-webui` on first use.

Open WebUI stores users, chats, uploads, connection settings, and cache data under `/srv/hermes/open-webui` by default. After first launch, Open WebUI persists connection settings in its data directory; make later connection changes in the Admin UI or reset the Open WebUI data directory intentionally.

Install `hermes-wiki` from the Hermes Agent dashboard after deployment:

```text
https://panel.rubiklab.vip
https://github.com/zombiearnie88/hermes-wiki.git
```

Or install from the Hermes Agent runtime:

```bash
docker compose -f examples/docker-compose.production-vps.yml exec -T -u 1000:1000 hermes-agent \
  /opt/hermes/.venv/bin/hermes plugins install --enable https://github.com/zombiearnie88/hermes-wiki.git
docker compose -f examples/docker-compose.production-vps.yml exec -T -u 1000:1000 hermes-agent \
  /opt/hermes/.venv/bin/hermes wiki deps --install all
```

Back up production data:

```bash
sudo tar -czf hermes-backup.tgz /srv/hermes
```

Update the stack images:

```bash
docker compose -f examples/docker-compose.production-vps.yml pull
docker compose -f examples/docker-compose.production-vps.yml up -d
```

## Production Mac Mini

`examples/mac-mini/` is a self-contained folder intended for Docker Desktop or a local Docker Engine on a Mac mini. It includes its own `docker-compose.yml`, `mac-mini.sh`, env example, and runbook.

Create a portable zip from the repo root:

```bash
(cd examples && zip -r ../hermes-wiki-mac-mini.zip mac-mini -x 'mac-mini/mac-mini.env' 'mac-mini/profiles.yaml' 'mac-mini/docker-compose.profiles.generated.yml' 'mac-mini/__pycache__/*' 'mac-mini/.DS_Store')
```

After unzipping on a Mac, start local-only access:

```bash
cd mac-mini
chmod +x mac-mini.sh
cp mac-mini.env.example mac-mini.env
vi mac-mini.env
./mac-mini.sh bootstrap-local
```

Replace `HERMES_API_SERVER_KEY` and `OPEN_WEBUI_SECRET_KEY` in `mac-mini.env` before starting. Generate values with `openssl rand -hex 32`.

Open the local single-stack frontends on the Mac mini:

```text
Hermes WebUI: http://127.0.0.1:8787
Open WebUI: http://127.0.0.1:3000
```

For LAN access:

```bash
./mac-mini.sh bootstrap-lan
```

LAN mode exposes both Hermes WebUI and Open WebUI to the trusted LAN. It does not publish the Hermes Agent API separately.

For the YAML-driven `code` and `research` profile stack:

```bash
./mac-mini.sh profiles-bootstrap-local
```

The profile stack is unchanged by the single-stack Open WebUI service.

Do not expose the Mac mini WebUIs directly to the public internet without a reverse proxy, TLS, and an access-control layer.

For full operation details, auth helpers, updates, backup, and troubleshooting, see `examples/mac-mini/README.md`.

## Production Volume Strategy

Production examples use this split:

| Data | Storage | Why |
|---|---|---|
| Hermes home/config/state | Host bind mount | Needs backup and inspection |
| Workspace/wiki data | Host bind mount | User/business data |
| Open WebUI data | Host bind mount | Users, chats, uploads, connection settings, and slim-image cache assets |
| Hermes Agent runtime | Docker named volume | Copied from the Agent image on first startup for WebUI use |
| Hermes WebUI Python venv | Docker named volume | Recreated by Hermes WebUI startup |
| Traefik cert state on VPS | Docker named volume | Managed by Traefik, can also be backed up separately |

Remove only containers while keeping data:

```bash
docker compose -f <compose-file> down
```

Remove containers and named runtime volumes:

```bash
docker compose -f <compose-file> down -v
```

`down -v` does not remove the host bind-mounted directories such as `/srv/hermes` or `/Users/Shared/hermes`.
