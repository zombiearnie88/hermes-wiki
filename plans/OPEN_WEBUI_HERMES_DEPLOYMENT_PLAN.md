# Open WebUI Hermes Deployment Plan

## Goal

Add Open WebUI as a second chat frontend for Hermes Agent, using the smaller Open WebUI slim image.

Target deployments:

- VPS production: `https://chat.rubiklab.vip`
- Mac Mini single-stack: local or LAN Open WebUI endpoint

Mac Mini profile mode is explicitly out of scope. The Mac Mini deployment should use only the existing single-stack services.

## Source Docs

- Open WebUI Hermes Agent guide: `https://docs.openwebui.com/getting-started/quick-start/connect-an-agent/hermes-agent`
- Hermes Agent Open WebUI guide: `https://hermes-agent.nousresearch.com/docs/user-guide/messaging/open-webui`
- Open WebUI quick start: `https://docs.openwebui.com/getting-started/quick-start/`

## Image Decision

Use this image by default:

```text
ghcr.io/open-webui/open-webui:main-slim
```

Known size and behavior:

- `main-slim` is about `1.43 GB` compressed for `linux/amd64`.
- `main-slim` is about `1.27 GB` compressed for `linux/arm64`.
- It saves about `266-279 MiB` compared with `main`.
- It skips pre-downloading Whisper, embedding, tiktoken, and NLTK cache assets.
- First use of RAG, speech-to-text, tokenizer, or related features may download assets into `/app/backend/data/cache`.

For production, keep the image configurable so the deployment can later pin a release tag or digest:

```text
OPEN_WEBUI_IMAGE=ghcr.io/open-webui/open-webui:main-slim
```

## Shared Architecture

Open WebUI should connect to Hermes Agent through the Docker network, not through a public API endpoint.

Recommended backend URL inside Docker:

```text
http://hermes-agent:8642/v1
```

Required Hermes API server settings:

```text
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8642
API_SERVER_MODEL_NAME=hermes-agent
API_SERVER_KEY=<same value used by Open WebUI>
```

Required Open WebUI settings:

```text
OPENAI_API_BASE_URL=http://hermes-agent:8642/v1
OPENAI_API_KEY=<same value as API_SERVER_KEY>
ENABLE_OLLAMA_API=false
```

Use Chat Completions mode by default. Responses API mode can be tested later, but it is not required for this deployment.

## Security Defaults

- Do not expose Hermes Agent API port `8642` publicly.
- Keep Open WebUI behind HTTPS on VPS.
- Disable Open WebUI signups by default on public VPS.
- Store Open WebUI data in a persistent host directory or named volume.
- Set a stable `WEBUI_SECRET_KEY` so sessions survive container recreation.
- Keep real `.env` files and generated secrets out of git.
- Rotate any secret that was pasted into tracked docs, chat logs, screenshots, or shared files.

## VPS Implementation

### Current VPS Stack

File to update:

```text
examples/docker-compose.production-vps.yml
```

Current public routes:

- `https://ai.rubiklab.vip` -> `hermes-webui:8787`
- `https://panel.rubiklab.vip` -> Hermes Agent dashboard on `9119`

New public route:

- `https://chat.rubiklab.vip` -> `open-webui:8080`

### DNS

Add DNS for `chat.rubiklab.vip`:

```text
chat.rubiklab.vip A <VPS_PUBLIC_IP>
```

If Cloudflare is used:

- Keep WebSockets enabled.
- Use an SSL mode compatible with the Traefik/Let's Encrypt origin certificate.
- Avoid proxy rules that buffer or break streaming responses.

### Compose Service

Add an `open-webui` service:

```yaml
  open-webui:
    image: ${OPEN_WEBUI_IMAGE:-ghcr.io/open-webui/open-webui:main-slim}
    restart: unless-stopped
    depends_on:
      hermes-agent:
        condition: service_started
    volumes:
      - ${OPEN_WEBUI_DATA_DIR:-/srv/hermes/open-webui}:/app/backend/data
    environment:
      WEBUI_URL: https://chat.rubiklab.vip
      WEBUI_NAME: RubikLab Chat
      WEBUI_SECRET_KEY: ${OPEN_WEBUI_SECRET_KEY:?Set OPEN_WEBUI_SECRET_KEY to a random secret}
      WEBUI_ADMIN_EMAIL: ${OPEN_WEBUI_ADMIN_EMAIL:?Set OPEN_WEBUI_ADMIN_EMAIL}
      WEBUI_ADMIN_PASSWORD: ${OPEN_WEBUI_ADMIN_PASSWORD:?Set OPEN_WEBUI_ADMIN_PASSWORD}
      ENABLE_SIGNUP: "false"
      ENABLE_OLLAMA_API: "false"
      OPENAI_API_BASE_URL: http://hermes-agent:8642/v1
      OPENAI_API_KEY: ${HERMES_API_SERVER_KEY:?Set HERMES_API_SERVER_KEY to a random secret}
    expose:
      - "8080"
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network=hermes-production-edge"
      - "traefik.http.routers.open-webui.rule=Host(`chat.rubiklab.vip`)"
      - "traefik.http.routers.open-webui.entrypoints=websecure"
      - "traefik.http.routers.open-webui.tls=true"
      - "traefik.http.routers.open-webui.tls.certresolver=le"
      - "traefik.http.services.open-webui.loadbalancer.server.port=8080"
    networks:
      - edge
      - internal
```

Do not publish a host port for `open-webui` on VPS. Traefik should be the only public entrypoint.

### VPS Environment

Update `examples/env.vps.example` with:

```text
# Open WebUI at https://chat.rubiklab.vip.
OPEN_WEBUI_IMAGE=ghcr.io/open-webui/open-webui:main-slim
OPEN_WEBUI_DATA_DIR=/srv/hermes/open-webui
OPEN_WEBUI_SECRET_KEY=replace-with-random-secret
OPEN_WEBUI_ADMIN_EMAIL=admin@rubiklab.vip
OPEN_WEBUI_ADMIN_PASSWORD=replace-with-random-password
```

Do not commit real values in `examples/.env.vps`.

Generate secrets with:

```bash
openssl rand -hex 32
```

### VPS Storage

Create persistent storage on the VPS:

```bash
sudo mkdir -p /srv/hermes/open-webui
sudo chown -R 1000:1000 /srv/hermes/open-webui
```

This directory stores Open WebUI users, chats, uploaded files, connection config, and downloaded slim-image cache assets.

### VPS Documentation Updates

Update these files:

- `examples/README.md`
- `examples/VPS_DEPLOY_CHECKLIST.md`
- `examples/env.vps.example`

Document:

- `https://chat.rubiklab.vip` as Open WebUI.
- DNS requirement for `chat.rubiklab.vip`.
- Open WebUI data directory backup requirement.
- Slim image cold-start behavior.
- Open WebUI environment settings are persisted after first launch; later connection changes should be done in the Admin UI or by resetting the Open WebUI data directory.

### VPS Verification

Run compose validation:

```bash
docker compose -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps config
```

Deploy:

```bash
docker compose -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps up -d
```

Check containers:

```bash
docker compose -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps ps
```

Check public route:

```bash
curl -I https://chat.rubiklab.vip
```

Check Hermes API from inside Open WebUI or another internal container:

```bash
curl -s http://hermes-agent:8642/health
curl -s -H "Authorization: Bearer ${HERMES_API_SERVER_KEY}" http://hermes-agent:8642/v1/models
```

Functional checks:

- Login to `https://chat.rubiklab.vip` with the configured admin account.
- Confirm model picker shows `hermes-agent`.
- Send a simple prompt.
- Send a prompt that triggers a harmless tool call and confirm streaming/progress behavior.

## Mac Mini Implementation

### Current Mac Mini Stack

File to update:

```text
examples/mac-mini/docker-compose.yml
```

Current single-stack route:

- Hermes WebUI: `http://127.0.0.1:8787`

New single-stack route:

- Open WebUI: `http://127.0.0.1:3000` by default

Profile mode is not used and should not be changed for this work.

### Hermes Agent Service

Update `hermes-agent` so it runs the gateway API instead of sleeping forever:

```yaml
    command:
      - gateway
      - run
    working_dir: /workspace
```

Add environment:

```yaml
      MESSAGING_CWD: /workspace
      API_SERVER_ENABLED: "true"
      API_SERVER_HOST: 0.0.0.0
      API_SERVER_PORT: "8642"
      API_SERVER_MODEL_NAME: hermes-agent
      API_SERVER_KEY: ${HERMES_API_SERVER_KEY:?Set HERMES_API_SERVER_KEY to a random secret}
```

The API does not need to be published to the Mac host. Open WebUI can reach it through Docker service DNS.

### Open WebUI Service

Add this service to `examples/mac-mini/docker-compose.yml`:

```yaml
  open-webui:
    image: ${OPEN_WEBUI_IMAGE:-ghcr.io/open-webui/open-webui:main-slim}
    restart: unless-stopped
    depends_on:
      hermes-agent:
        condition: service_started
    ports:
      - "${OPEN_WEBUI_BIND_IP:-127.0.0.1}:${OPEN_WEBUI_PORT:-3000}:8080"
    volumes:
      - ${OPEN_WEBUI_DATA_DIR:-/Users/Shared/hermes/open-webui}:/app/backend/data
    environment:
      WEBUI_URL: ${OPEN_WEBUI_URL:-http://127.0.0.1:3000}
      WEBUI_NAME: ${OPEN_WEBUI_NAME:-RubikLab Chat}
      WEBUI_SECRET_KEY: ${OPEN_WEBUI_SECRET_KEY:?Set OPEN_WEBUI_SECRET_KEY to a random secret}
      ENABLE_OLLAMA_API: "false"
      OPENAI_API_BASE_URL: http://hermes-agent:8642/v1
      OPENAI_API_KEY: ${HERMES_API_SERVER_KEY:?Set HERMES_API_SERVER_KEY to a random secret}
    networks:
      - hermes-private
```

Keep Open WebUI authentication defaults unless a specific admin auto-create flow is required. For local Mac Mini use, first-user-admin signup is acceptable if the endpoint is loopback-only.

### Mac Mini Environment

Update `examples/mac-mini/mac-mini.env.example`:

```text
# Hermes API used by Open WebUI. Generate with: openssl rand -hex 32
HERMES_API_SERVER_KEY=replace-with-random-secret

# Open WebUI at http://127.0.0.1:3000 by default.
OPEN_WEBUI_IMAGE=ghcr.io/open-webui/open-webui:main-slim
OPEN_WEBUI_BIND_IP=127.0.0.1
OPEN_WEBUI_PORT=3000
OPEN_WEBUI_URL=http://127.0.0.1:3000
OPEN_WEBUI_NAME=RubikLab Chat
OPEN_WEBUI_DATA_DIR=/Users/Shared/hermes/open-webui
OPEN_WEBUI_SECRET_KEY=replace-with-random-secret
```

### Mac Mini Script Updates

Update `examples/mac-mini/mac-mini.sh` for single-stack only:

- Load and export `HERMES_API_SERVER_KEY`.
- Load and export `OPEN_WEBUI_IMAGE`.
- Load and export `OPEN_WEBUI_BIND_IP`.
- Load and export `OPEN_WEBUI_PORT`.
- Load and export `OPEN_WEBUI_URL`.
- Load and export `OPEN_WEBUI_NAME`.
- Load and export `OPEN_WEBUI_DATA_DIR`.
- Load and export `OPEN_WEBUI_SECRET_KEY`.
- Include `OPEN_WEBUI_DATA_DIR` in `init_storage`.
- Check `OPEN_WEBUI_PORT` in `preflight`.
- Print Open WebUI URL in `up_local` and `up_lan`.
- Wait for Open WebUI in `wait_ready`.
- Verify Open WebUI HTTP response in `verify`.
- Include `open-webui` in `logs`, `restart`, `pull`, and update flows.

For LAN mode:

- Set `OPEN_WEBUI_BIND_IP=0.0.0.0`.
- Set `OPEN_WEBUI_URL=http://<mac-lan-ip>:3000` in printed output or docs.
- Do not expose Hermes API separately on the LAN.

### Mac Mini Documentation Updates

Update these files:

- `examples/mac-mini/README.md`
- `examples/README.md`

Document:

- Hermes WebUI remains available on `8787`.
- Open WebUI is available on `3000` by default.
- LAN mode exposes Open WebUI and Hermes WebUI to the trusted LAN.
- Open WebUI data lives under `/Users/Shared/hermes/open-webui` by default.
- Slim image may download RAG/STT/tokenizer assets on first use.

### Mac Mini Verification

Validate compose:

```bash
docker compose -f examples/mac-mini/docker-compose.yml --env-file examples/mac-mini/mac-mini.env config
```

Bootstrap local:

```bash
cd examples/mac-mini
./mac-mini.sh bootstrap-local
```

Check URLs:

```bash
curl -fsS -o /dev/null http://127.0.0.1:8787
curl -fsS -o /dev/null http://127.0.0.1:3000
```

Check Hermes API from inside Open WebUI or another container:

```bash
docker compose -p hermes-mac-mini -f examples/mac-mini/docker-compose.yml exec -T open-webui \
  bash -lc 'curl -s http://hermes-agent:8642/health'
```

Functional checks:

- Open `http://127.0.0.1:3000`.
- Create the first admin account if auto-admin is not configured.
- Confirm model picker shows `hermes-agent`.
- Send a simple test prompt.
- Confirm a harmless tool-call prompt runs on the Mac Mini container workspace.

## Implementation Order

1. Update VPS compose and docs.
2. Validate VPS compose config locally.
3. Update Mac Mini compose, env example, script, and docs.
4. Validate Mac Mini compose config locally.
5. Deploy VPS after DNS for `chat.rubiklab.vip` is ready.
6. Bootstrap Mac Mini local mode and verify both WebUIs.
7. Test LAN mode only on a trusted LAN.

## Acceptance Criteria

- `https://chat.rubiklab.vip` serves Open WebUI through Traefik on VPS.
- VPS Open WebUI uses `ghcr.io/open-webui/open-webui:main-slim` by default.
- VPS Open WebUI connects to Hermes Agent through `http://hermes-agent:8642/v1`.
- Mac Mini Open WebUI is available on port `3000` by default.
- Mac Mini Open WebUI connects to the single Hermes Agent service through Docker DNS.
- Mac Mini profile stack is unchanged by this work.
- Hermes API is not publicly exposed.
- Open WebUI data is persistent and included in deployment backup guidance.
