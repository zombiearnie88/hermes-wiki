# Hermes Wiki Mac Mini Bundle

This folder is a self-contained Mac mini deployment bundle. Zip this folder, copy it to another Mac, unzip it, and run `mac-mini.sh` from inside the folder.

The single-stack bundle starts Hermes Agent, Hermes WebUI, and Open WebUI with Docker Compose. Persistent user data is stored under `/Users/Shared/hermes` by default. Runtime internals stay in Docker named volumes.

## Files

```text
mac-mini/
  README.md
  docker-compose.yml
  docker-compose.profiles.generated.yml
  generate-profiles-compose.py
  mac-mini.env.example
  mac-mini.sh
  profiles.yaml.example
```

`docker-compose.profiles.generated.yml` is generated locally from `profiles.yaml` or `profiles.yaml.example` and is ignored by git.

## Create A Zip

From the repo root:

```bash
(cd examples && zip -r ../hermes-wiki-mac-mini.zip mac-mini -x 'mac-mini/mac-mini.env' 'mac-mini/profiles.yaml' 'mac-mini/docker-compose.profiles.generated.yml' 'mac-mini/__pycache__/*' 'mac-mini/.DS_Store')
```

Do not include `mac-mini.env`, `profiles.yaml`, or generated compose output in the zip unless you intentionally want to copy machine-specific settings.

## First Run On A Mac

Unzip the bundle and enter the folder:

```bash
cd mac-mini
chmod +x mac-mini.sh
cp mac-mini.env.example mac-mini.env
vi mac-mini.env
```

Replace `HERMES_API_SERVER_KEY` and `OPEN_WEBUI_SECRET_KEY` before the first single-stack deploy. Generate values with `openssl rand -hex 32`.

Local-only deployment:

```bash
./mac-mini.sh bootstrap-local
```

Open the local single-stack frontends on the Mac:

```text
Hermes WebUI: http://127.0.0.1:8787
Open WebUI: http://127.0.0.1:3000
```

LAN deployment:

```bash
./mac-mini.sh bootstrap-lan
```

Open the single-stack frontends from another device on the LAN:

```text
Hermes WebUI: http://<mac-lan-ip>:8787
Open WebUI: http://<mac-lan-ip>:3000
```

LAN mode exposes Hermes WebUI and Open WebUI to the trusted LAN. It does not publish the Hermes Agent API separately.

Open WebUI uses first-user-admin signup by default in this local bundle. Keep the endpoint loopback-only unless the LAN is trusted.

Do not expose the Mac mini WebUIs directly to the public internet without a reverse proxy, TLS, and an access-control layer.

## Env File

Create `mac-mini.env` from `mac-mini.env.example` before running the single-stack Open WebUI deployment. The example file contains these values and placeholders; replace the secret placeholders before bootstrapping:

```text
HERMES_COMPOSE_PROJECT=hermes-mac-mini
HERMES_PROFILES_COMPOSE_PROJECT=hermes-mac-mini-profiles
HERMES_PROFILES_BASE_DIR=/Users/Shared/hermes/profiles
HERMES_API_SERVER_KEY=replace-with-random-secret
HERMES_WEBUI_BIND_IP=127.0.0.1
HERMES_WEBUI_PORT=8787
HERMES_HOME_DIR=/Users/Shared/hermes/home
HERMES_WORKSPACE_DIR=/Users/Shared/hermes/workspace
HERMES_WIKI_REPO=https://github.com/zombiearnie88/hermes-wiki.git
OPEN_WEBUI_IMAGE=ghcr.io/open-webui/open-webui:main-slim
OPEN_WEBUI_BIND_IP=127.0.0.1
OPEN_WEBUI_PORT=3000
OPEN_WEBUI_URL=http://127.0.0.1:3000
OPEN_WEBUI_NAME=RubikLab Chat
OPEN_WEBUI_DATA_DIR=/Users/Shared/hermes/open-webui
OPEN_WEBUI_SECRET_KEY=replace-with-random-secret
```

Open WebUI stores users, chats, uploads, connection settings, and downloaded slim-image cache assets under `/Users/Shared/hermes/open-webui` by default. The slim image may download RAG, speech-to-text, tokenizer, or related assets on first use.

`HERMES_WIKI_REPO` is used by the generated multi-profile stack, not by the single-stack `docker-compose.yml`.

## Multi-Profile Stack

The bundle can also run multiple isolated Hermes profiles from a YAML config. Docker Compose cannot create services dynamically by itself, so `mac-mini.sh` generates `docker-compose.profiles.generated.yml` from `profiles.yaml`.

The profile stack is unchanged by the single-stack Open WebUI service.

Each profile gets its own Hermes Agent gateway container and WebUI container, while all profiles share the `hermes-agent-src` runtime volume. This follows the Hermes Docker recommendation to use one container per profile instead of built-in profiles inside one container.

If `profiles.yaml` is absent, the script uses `profiles.yaml.example`, which defines `code` and `research` profiles.

Default local URLs:

```text
Code WebUI: http://127.0.0.1:8787
Research WebUI: http://127.0.0.1:8788
Code gateway API: http://127.0.0.1:8642
Research gateway API: http://127.0.0.1:8643
Code dashboard: http://127.0.0.1:9119
Research dashboard: http://127.0.0.1:9120
```

Start the profile stack locally:

```bash
./mac-mini.sh profiles-bootstrap-local
```

Start the profile stack on the LAN:

```bash
./mac-mini.sh profiles-bootstrap-lan
```

After a profile bootstrap verifies successfully, the script automatically removes completed one-shot setup containers. To clean them up manually:

```bash
./mac-mini.sh profiles-cleanup
```

This preserves running profile containers, Docker named volumes, and host data under `/Users/Shared/hermes`.

Customize profiles:

```bash
cp profiles.yaml.example profiles.yaml
vi profiles.yaml
./mac-mini.sh profiles-generate
./mac-mini.sh profiles-bootstrap-local
```

Supported `profiles.yaml` fields:

```yaml
profiles:
  - id: code
    webui_port: 8787
    gateway_port: 8642
    dashboard_port: 9119
    bind_ip: 127.0.0.1
    home_dir: /Users/Shared/hermes/profiles/code/home
    workspace_dir: /Users/Shared/hermes/profiles/code/workspace
    dashboard_tui: false
    api_server_key: local-code-api-key
```

`home_dir` and `workspace_dir` are optional. If omitted, they default to `${HERMES_PROFILES_BASE_DIR}/<id>/home` and `${HERMES_PROFILES_BASE_DIR}/<id>/workspace`.

If the Mac has `python3`, the script uses it to generate compose. Otherwise it falls back to the small `python:3.13-alpine` Docker image.

For profile-only deployments, create an env file only when you need custom values:

```bash
cp mac-mini.env.example mac-mini.env
vi mac-mini.env
```

Check UID/GID manually if you override them:

```bash
id -u
id -g
```

## Hermes CLI Aliases

Run Hermes command-line tools through the profile agent containers. From the `mac-mini` bundle directory:

```bash
export HERMES_MAC_MINI_DIR="$(pwd)"

alias hermes-code='docker compose -p hermes-mac-mini-profiles -f "$HERMES_MAC_MINI_DIR/docker-compose.profiles.generated.yml" exec -w /workspace hermes-agent-code /opt/hermes/.venv/bin/hermes'
alias hermes-research='docker compose -p hermes-mac-mini-profiles -f "$HERMES_MAC_MINI_DIR/docker-compose.profiles.generated.yml" exec -w /workspace hermes-agent-research /opt/hermes/.venv/bin/hermes'
```

For persistent aliases, add the same lines to `~/.zshrc` or `~/.bashrc`, but set `HERMES_MAC_MINI_DIR` to the absolute path of this bundle.

Example usages:

```bash
hermes-code tools
hermes-code plugins list
hermes-code auth list
hermes-code status
hermes-research tools
hermes-research auth list
```

For non-interactive scripts, add `-T` after `exec`:

```bash
docker compose -p hermes-mac-mini-profiles -f "$HERMES_MAC_MINI_DIR/docker-compose.profiles.generated.yml" exec -T -w /workspace hermes-agent-code /opt/hermes/.venv/bin/hermes tools
```

## Commands

```bash
./mac-mini.sh bootstrap-local
./mac-mini.sh bootstrap-lan
./mac-mini.sh profiles-generate
./mac-mini.sh profiles-bootstrap-local
./mac-mini.sh profiles-bootstrap-lan
./mac-mini.sh profiles-preflight
./mac-mini.sh profiles-init-storage
./mac-mini.sh profiles-up-local
./mac-mini.sh profiles-up-lan
./mac-mini.sh profiles-wait-ready
./mac-mini.sh profiles-verify
./mac-mini.sh profiles-ps
./mac-mini.sh profiles-logs
./mac-mini.sh profiles-cleanup
./mac-mini.sh profiles-down
./mac-mini.sh profiles-down-volumes
./mac-mini.sh preflight
./mac-mini.sh init-storage
./mac-mini.sh up-local
./mac-mini.sh up-lan
./mac-mini.sh wait-ready
./mac-mini.sh verify
./mac-mini.sh auth-providers
./mac-mini.sh auth --help
./mac-mini.sh auth list
./mac-mini.sh ps
./mac-mini.sh logs
./mac-mini.sh restart
./mac-mini.sh update
./mac-mini.sh pull
./mac-mini.sh down
./mac-mini.sh down-volumes
```

## Auth

List auth providers from the running Hermes Agent runtime:

```bash
./mac-mini.sh auth-providers
```

Run Hermes auth commands inside the Hermes Agent container:

```bash
./mac-mini.sh auth --help
./mac-mini.sh auth list
./mac-mini.sh auth status <provider>
./mac-mini.sh auth spotify
```

## Updates

Recreate single-stack runtime services after env or compose changes:

```bash
./mac-mini.sh update
```

For generated profile-stack plugin installs, change `HERMES_WIKI_REPO` in `mac-mini.env` before regenerating or bootstrapping profiles:

```text
HERMES_WIKI_REPO=https://github.com/zombiearnie88/hermes-wiki.git
```

Pull newer base images and recreate containers:

```bash
./mac-mini.sh pull
```

## Backup

Back up persistent production data:

```bash
sudo tar -czf hermes-mac-mini-backup.tgz /Users/Shared/hermes
```

If you set custom `HERMES_HOME_DIR`, `HERMES_WORKSPACE_DIR`, or `OPEN_WEBUI_DATA_DIR`, back up those directories instead.

## Stop Or Remove

Stop and remove containers while keeping host data and named runtime volumes:

```bash
./mac-mini.sh down
```

Remove containers and named runtime volumes:

```bash
./mac-mini.sh down-volumes
```

`down-volumes` removes Docker named volumes such as `hermes-agent-src` and `hermes-webui-venv`. It does not remove host bind-mounted data under `/Users/Shared/hermes`.

Remove host data only when you intentionally want to delete Hermes configuration, auth, sessions, logs, workspaces, and wiki data. Back it up first, then remove `/Users/Shared/hermes` manually.

## Troubleshooting

If `8787` or `3000` is already in use, change `HERMES_WEBUI_PORT` or `OPEN_WEBUI_PORT` in `mac-mini.env`, then redeploy:

```bash
./mac-mini.sh up-local
```

If bind-mounted files are owned by the wrong user, confirm UID/GID and rerun:

```bash
./mac-mini.sh init-storage
```

If a runtime service fails, inspect logs and recreate services:

```bash
./mac-mini.sh logs
./mac-mini.sh update
```

If WebUI starts slowly on first run, wait for dependency installation to finish:

```bash
./mac-mini.sh wait-ready
./mac-mini.sh verify
```
