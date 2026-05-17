# VPS Deploy Checklist

This checklist is tailored for the current production VPS deployment:

- `ai.rubiklab.vip` -> Hermes WebUI
- `panel.rubiklab.vip` -> Hermes Agent dashboard, protected by Traefik BasicAuth
- Docker context: `hermes-agent`
- VPS host: `opc@161.118.197.15`
- SSH key: `~/dev/machine-learning/.ssh/kgraph-ai-2.key`

## Files Used

- Compose file: `examples/docker-compose.production-vps.yml`
- Env example: `examples/env.vps.example`
- Runtime env file: `examples/.env.vps`

## One-Time Preparation

- [ ] Copy `examples/env.vps.example` to `examples/.env.vps`
- [ ] Update `ACME_EMAIL` in `examples/.env.vps`
- [ ] Replace `HERMES_WEBUI_PASSWORD` in `examples/.env.vps`
- [ ] Confirm `HERMES_DASHBOARD_BASIC_AUTH` is set in `examples/.env.vps`
- [ ] Confirm DNS points both hostnames to `161.118.197.15`
- [ ] Confirm OCI ingress and host firewall allow `80/tcp` and `443/tcp`
- [ ] Confirm Docker context `hermes-agent` is reachable

## Local Docker Context

Ensure `~/.ssh/config` has this host alias:

```sshconfig
Host hermes-agent-vps
  HostName 161.118.197.15
  User opc
  IdentityFile ~/dev/machine-learning/.ssh/kgraph-ai-2.key
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
```

Create the Docker context if it does not already exist:

```bash
docker context create hermes-agent \
  --description "Hermes Agent VPS opc@161.118.197.15" \
  --docker "host=ssh://hermes-agent-vps"
```

## Generate Secrets

Generate a new Hermes API key if you do not want to use the example value:

```bash
openssl rand -hex 32
```

Generate a new dashboard BasicAuth password and hash:

```bash
openssl rand -base64 18
openssl passwd -apr1 '<password-from-previous-command>'
```

When storing an APR1 hash in `examples/.env.vps`, double each dollar sign as `$$` so Docker Compose does not treat it as variable interpolation.

## Verify DNS

- [ ] Check `ai.rubiklab.vip`
- [ ] Check `panel.rubiklab.vip`

```bash
dig +short ai.rubiklab.vip
dig +short panel.rubiklab.vip
```

Expected result: both resolve to `161.118.197.15`.

## Verify Remote Access

- [ ] Verify Docker context access
- [ ] Verify SSH access
- [ ] Verify remote user UID/GID

```bash
docker --context hermes-agent info
ssh hermes-agent-vps 'id -u && id -g'
```

Expected result:

- Docker info returns successfully
- SSH works
- UID/GID is `1000/1000`

## Create Host Directories

- [ ] Create Hermes data directories on the VPS
- [ ] Ensure ownership is `1000:1000`

```bash
ssh hermes-agent-vps 'sudo mkdir -p /srv/hermes/home /srv/hermes/workspace'
ssh hermes-agent-vps 'sudo chown -R 1000:1000 /srv/hermes'
```

## Validate Compose Locally Before Deploy

- [ ] Validate compose rendering with `examples/.env.vps`
- [ ] Confirm only `traefik`, `hermes-agent`, and `hermes-webui` are present

```bash
docker compose -p hermes-production -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps config
docker compose -p hermes-production -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps config --services
```

Expected services:

```text
hermes-agent
hermes-webui
traefik
```

## Deploy To The VPS

- [ ] Pull current images on the VPS
- [ ] Start the production stack

```bash
docker --context hermes-agent compose -p hermes-production -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps pull
docker --context hermes-agent compose -p hermes-production -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps up -d
```

## Check Runtime Status

- [ ] Check Compose state
- [ ] Check Traefik logs
- [ ] Check Hermes Agent logs
- [ ] Check Hermes WebUI logs

```bash
docker --context hermes-agent compose -p hermes-production -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps ps
docker --context hermes-agent compose -p hermes-production -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps logs -f traefik
docker --context hermes-agent compose -p hermes-production -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps logs -f hermes-agent
docker --context hermes-agent compose -p hermes-production -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps logs -f hermes-webui
```

## Validate Public Endpoints

- [ ] Check WebUI public URL
- [ ] Check dashboard public URL requires BasicAuth

```bash
curl -I https://ai.rubiklab.vip
curl -I https://panel.rubiklab.vip
curl -I -u 'admin:<dashboard-password>' https://panel.rubiklab.vip
```

Then open in browser:

- `https://ai.rubiklab.vip`
- `https://panel.rubiklab.vip`

## Install Hermes Wiki Plugin

- [ ] Open `https://panel.rubiklab.vip`
- [ ] Authenticate with dashboard BasicAuth
- [ ] Install and enable the `hermes-wiki` plugin from the Hermes Agent dashboard with `https://github.com/zombiearnie88/hermes-wiki.git`
- [ ] Run dependency setup in the Hermes Agent runtime
- [ ] Restart Hermes Agent and WebUI

CLI equivalent:

```bash
docker --context hermes-agent compose -p hermes-production -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps exec -T -u 1000:1000 hermes-agent \
  /opt/hermes/.venv/bin/hermes plugins install --force --enable https://github.com/zombiearnie88/hermes-wiki.git
docker --context hermes-agent compose -p hermes-production -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps exec -T -u 1000:1000 hermes-agent \
  /opt/hermes/.venv/bin/hermes wiki deps --install all
docker --context hermes-agent compose -p hermes-production -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps restart hermes-agent hermes-webui
```

Expected plugin list entry after restart:

```text
hermes-wiki    enabled    0.1.1    user
```

## SELinux Fallback

If containers fail with permission errors on `/srv/hermes`, apply the container label and retry.

- [ ] Relabel `/srv/hermes` for containers if needed

```bash
ssh hermes-agent-vps 'sudo chcon -Rt svirt_sandbox_file_t /srv/hermes'
```

## Rollback / Stop

- [ ] Stop the VPS stack if needed

```bash
docker --context hermes-agent compose -p hermes-production -f examples/docker-compose.production-vps.yml --env-file examples/.env.vps down
```

## Final Sanity Check

- [ ] `examples/.env.vps` has the correct `ACME_EMAIL`
- [ ] `examples/.env.vps` has a strong `HERMES_API_SERVER_KEY`
- [ ] `examples/.env.vps` has a strong `HERMES_WEBUI_PASSWORD`
- [ ] `examples/.env.vps` has `HERMES_DASHBOARD_BASIC_AUTH`
- [ ] DNS resolves both domains to `161.118.197.15`
- [ ] `/srv/hermes/home` exists and is owned by `1000:1000`
- [ ] `/srv/hermes/workspace` exists and is owned by `1000:1000`
- [ ] `docker --context hermes-agent compose ... ps` shows all services up
- [ ] `https://ai.rubiklab.vip` loads
- [ ] `https://panel.rubiklab.vip` prompts for BasicAuth and loads after login
