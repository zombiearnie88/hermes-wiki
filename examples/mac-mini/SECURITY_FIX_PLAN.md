# Mac Mini Docker Security Fix Plan

This plan captures the security fixes identified from comparing the Mac mini Docker bundle with the Hermes security guide.

## Goals

- Preserve the current local-first Mac mini workflow.
- Keep LAN exposure explicit and narrow.
- Align runtime containers with Hermes container-hardening guidance.
- Reduce the chance that copied example defaults become production secrets.

## Priority Fixes

### 1. Harden Runtime Containers

Apply Docker hardening to long-running runtime services in both `docker-compose.yml` and `generate-profiles-compose.py` output.

Target services:

- `hermes-agent`
- `hermes-webui`
- generated `hermes-agent-<profile>` services
- generated `hermes-webui-<profile>` services

Add where compatible with image entrypoints:

```yaml
cap_drop:
  - ALL
security_opt:
  - no-new-privileges:true
pids_limit: 256
  - /tmp:rw,nosuid,size=512m
  - /var/tmp:rw,noexec,nosuid,size=256m
  - /run:rw,noexec,nosuid,size=64m
```

Also add configurable CPU and memory limits, for example `HERMES_CONTAINER_CPUS` and `HERMES_CONTAINER_MEMORY`.

### 2. Keep Gateway And Dashboard Loopback-Only By Default

Change profile LAN mode so it only exposes WebUI on the LAN by default.

Current risk:

- `profiles-bootstrap-lan` overrides every generated bind IP to `0.0.0.0`.
- This exposes WebUI, gateway API, and dashboard together.

Target behavior:

- WebUI may bind to `0.0.0.0` in LAN mode.
- Gateway API remains bound to `127.0.0.1` unless explicitly configured.
- Dashboard remains bound to `127.0.0.1` unless explicitly configured.

Implementation approach:

- Split profile bind fields into `webui_bind_ip`, `gateway_bind_ip`, and `dashboard_bind_ip`.
- Keep backwards compatibility for `bind_ip` only if needed for existing local profile files.
- Make `profiles-up-lan` override only `webui_bind_ip`.

### 3. Replace Example API Keys With Required Secrets

The generated profile compose currently embeds values like `local-code-api-key` and `local-research-api-key`.

Fixes:

- Remove default API keys from generated production output.
- Require `api_server_key` in `profiles.yaml` when API publishing is enabled.
- Validate that keys are not known example values.
- Document generating random keys with `openssl rand -hex 32`.

### 4. Restrict API CORS

Change generated profile services from wildcard CORS to a configured allowlist.

Current setting:

```yaml
API_SERVER_CORS_ORIGINS: "*"
```

Target behavior:

- Default to local WebUI origins only.
- Allow explicit per-profile `api_server_cors_origins` when needed.
- Fail generation if LAN/public API exposure uses wildcard CORS.

### 5. Set Agent Working Directory

Follow the Hermes security guide recommendation to avoid sensitive default working directories.

Add to gateway services:

```yaml
working_dir: /workspace
  MESSAGING_CWD: /workspace
```

Apply to:

- generated `hermes-agent-<profile>` services
- any future single-stack gateway service if added

### 6. Remove World-Writable WebUI Virtualenv Permissions

Replace this installer behavior:

```sh
chmod -R a+rwX /app/venv
```

Preferred behavior:

```sh
chown -R "$${HERMES_UID}:$${HERMES_GID}" /app/venv
chmod -R u+rwX,go-rwx /app/venv
```

If the WebUI image requires a different runtime user, map ownership to that user instead of using world-writable permissions.

### 7. Pin Production Artifacts

Avoid mutable runtime inputs in production examples.

Fixes:

- Replace `:latest` image references with configurable pinned tags.
- Document digest pinning for production deployments.
- Keep `HERMES_WIKI_REPO` pointed at the approved plugin repository or an immutable release ref when supported.

## Documentation Updates

Update `README.md` and `mac-mini.env.example` to document:

- LAN mode exposes network services and should only be used on trusted networks.
- Gateway API and dashboard should stay loopback-only unless intentionally exposed behind auth and TLS.
- Production profile API keys must be random secrets.
- Public internet exposure requires reverse proxy, TLS, and access control.
- Persistent data under `/Users/Shared/hermes` contains credentials, sessions, logs, and workspaces and should be backed up and permissioned carefully.

## Verification

After implementing fixes, verify:

- `./mac-mini.sh bootstrap-local` still works.
- `./mac-mini.sh profiles-bootstrap-local` still works.
- `./mac-mini.sh profiles-bootstrap-lan` exposes only WebUI on LAN by default.
- `docker inspect` shows `no-new-privileges`, dropped capabilities, PID limits, and tmpfs mounts on runtime containers.
- Generated compose rejects weak or missing profile API keys when gateway API exposure is enabled.
- WebUI package import verification still passes after removing world-writable virtualenv permissions.
