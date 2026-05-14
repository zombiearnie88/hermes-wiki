# Examples

## Which Compose File To Use

| File | Use Case | Persistent Data Location |
|---|---|---|
| `docker-compose.pip.yml` | Fresh local smoke test from GitHub install | Docker named volumes only |
| `docker-compose.production-vps.yml` | Public VPS deployment with HTTPS through Caddy | Host bind mounts under `/srv/hermes` by default |
| `docker-compose.production-mac-mini.yml` | Mac mini deployment for local or LAN access | Host bind mounts under `/Users/Shared/hermes` by default |

For production, back up the host bind-mounted directories. The named volumes in these examples are runtime internals that can be recreated.

## Fresh Docker Pip Install

`docker-compose.pip.yml` starts a clean Hermes Agent and WebUI stack that installs `hermes-wiki` from GitHub with `uv pip install`.

It intentionally does not reuse the repo-local `docker/` directory, existing profiles, auth files, workspaces, or bind-mounted plugin source.

Start it:

```bash
docker compose -f examples/docker-compose.pip.yml up -d
```

Open WebUI:

```text
http://127.0.0.1:8787
```

Pin a release tag:

```bash
HERMES_WIKI_PACKAGE='git+https://github.com/zombiearnie88/hermes-wiki.git@v0.1.0' \
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

Verify the package import in the WebUI runtime:

```bash
docker compose -f examples/docker-compose.pip.yml exec -u 0 hermes-webui \
  /app/venv/bin/python3 -c "import hermes_wiki; assert callable(hermes_wiki.register)"
```

Reset all example state:

```bash
docker compose -f examples/docker-compose.pip.yml down -v
```

This removes the named volumes used by the example, including Hermes home, WebUI venv, and workspace state.

## Production VPS

`docker-compose.production-vps.yml` is intended for a public VPS with DNS pointing at the server. It exposes only Caddy on ports `80` and `443`; `hermes-webui` is reachable only inside the Docker network.

Create persistent host directories:

```bash
sudo mkdir -p /srv/hermes/home /srv/hermes/workspace
sudo chown -R 1000:1000 /srv/hermes
```

Set deployment variables:

```bash
export HERMES_DOMAIN=hermes.example.com
export HERMES_WIKI_PACKAGE='git+https://github.com/zombiearnie88/hermes-wiki.git@v0.1.0'
```

Start it:

```bash
docker compose -f examples/docker-compose.production-vps.yml up -d
```

Verify plugin state in the Hermes Agent runtime:

```bash
docker compose -f examples/docker-compose.production-vps.yml exec hermes-agent \
  /opt/hermes/.venv/bin/hermes plugins list
```

Verify the package import in the WebUI runtime:

```bash
docker compose -f examples/docker-compose.production-vps.yml exec -u 0 hermes-webui \
  /app/venv/bin/python3 -c "import hermes_wiki; assert callable(hermes_wiki.register)"
```

Back up production data:

```bash
sudo tar -czf hermes-backup.tgz /srv/hermes
```

Update to a new plugin tag:

```bash
export HERMES_WIKI_PACKAGE='git+https://github.com/zombiearnie88/hermes-wiki.git@v0.1.1'
docker compose -f examples/docker-compose.production-vps.yml up -d --force-recreate \
  hermes-agent-plugin-install hermes-webui-plugin-install
docker compose -f examples/docker-compose.production-vps.yml restart hermes-agent hermes-webui
```

## Production Mac Mini

`docker-compose.production-mac-mini.yml` is intended for Docker Desktop or a local Docker Engine on a Mac mini. It does not include Caddy. By default it binds WebUI to `127.0.0.1:8787`.

Create persistent host directories:

```bash
sudo mkdir -p /Users/Shared/hermes/home /Users/Shared/hermes/workspace
sudo chown -R $(id -u):$(id -g) /Users/Shared/hermes
```

Set a pinned plugin package:

```bash
export HERMES_WIKI_PACKAGE='git+https://github.com/zombiearnie88/hermes-wiki.git@v0.1.0'
```

Start it for local-only access:

```bash
docker compose -f examples/docker-compose.production-mac-mini.yml up -d
```

Open WebUI on the Mac mini:

```text
http://127.0.0.1:8787
```

To expose WebUI on your LAN, bind to all interfaces:

```bash
HERMES_WEBUI_BIND_IP=0.0.0.0 docker compose -f examples/docker-compose.production-mac-mini.yml up -d
```

Do not expose the Mac mini WebUI directly to the public internet without a reverse proxy, TLS, and an access-control layer.

Back up production data:

```bash
sudo tar -czf hermes-mac-mini-backup.tgz /Users/Shared/hermes
```

## Production Volume Strategy

Production examples use this split:

| Data | Storage | Why |
|---|---|---|
| Hermes home/config/state | Host bind mount | Needs backup and inspection |
| Workspace/wiki data | Host bind mount | User/business data |
| Hermes Agent runtime | Docker named volume | Recreated from image |
| WebUI Python venv | Docker named volume | Recreated by install service |
| Caddy cert state on VPS | Docker named volume | Managed by Caddy, can also be backed up separately |

Remove only containers while keeping data:

```bash
docker compose -f <compose-file> down
```

Remove containers and named runtime volumes:

```bash
docker compose -f <compose-file> down -v
```

`down -v` does not remove the host bind-mounted directories such as `/srv/hermes` or `/Users/Shared/hermes`.
