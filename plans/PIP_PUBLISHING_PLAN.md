# Pip Publishing Plan

## Goal

Distribute `hermes-wiki` as a pip-installable Hermes plugin from the GitHub repo at `https://github.com/zombiearnie88/hermes-wiki.git`, while keeping the repo useful for local development, Docker examples, tests, and release validation.

## Decision

Publish the repo root as the package source, not only the `hermes_wiki/` directory.

The repo root should contain packaging metadata and docs:

```text
hermes-wiki/
  pyproject.toml
  README.md
  LICENSE
  .gitignore
  hermes_wiki/
  examples/
  tests/
  plans/
```

The runtime package remains limited to `hermes_wiki/` through `pyproject.toml`:

```toml
[tool.hatch.build.targets.wheel]
packages = ["hermes_wiki"]
```

This lets GitHub host docs, examples, and tests without installing those folders into the Hermes runtime.

## Current Package Contract

`pyproject.toml` already declares the Hermes plugin entry point:

```toml
[project.entry-points."hermes_agent.plugins"]
hermes-wiki = "hermes_wiki"
```

After installation into the same Python environment that Hermes uses, Hermes can discover the plugin through Python package entry points. Pip installation does not copy the plugin into `~/.hermes/plugins/hermes-wiki/`; that directory is only for directory-plugin installs.

## What Install Does

Running this command:

```bash
uv pip install git+https://github.com/zombiearnie88/hermes-wiki.git
```

causes `uv` to:

1. Clone the GitHub repo into a temporary build directory.
2. Read root `pyproject.toml`.
3. Build the package with Hatchling.
4. Install the `hermes_wiki` Python package.
5. Install declared dependencies such as `json-repair`, `pymupdf`, and `markitdown[all]`.
6. Install the `hermes-wiki` standalone CLI script.
7. Register the `hermes_agent.plugins` entry point named `hermes-wiki`.

For Hermes deployments, always target the Hermes runtime Python explicitly:

```bash
uv pip install --python /opt/hermes/.venv/bin/python git+https://github.com/zombiearnie88/hermes-wiki.git
/opt/hermes/.venv/bin/hermes plugins enable hermes-wiki
```

Use the WebUI runtime Python separately when WebUI imports plugins from its own virtualenv:

```bash
uv pip install --python /app/venv/bin/python3 git+https://github.com/zombiearnie88/hermes-wiki.git
```

## Files To Publish

Keep these in the GitHub repo:

```text
pyproject.toml
README.md
LICENSE
AGENTS.md
hermes_wiki/
examples/
tests/
plans/
```

Do not publish local runtime state or secrets:

```text
.venv/
__pycache__/
.pytest_cache/
docker/data/
docker/.env
raw/
wiki/
.hermeskb/
dist/
*.egg-info/
```

Avoid publishing `code-donor/` unless the donor references are intentionally part of the public development repo. They are not runtime dependencies of the pip package.

## Release Workflow

1. Confirm the package version in `pyproject.toml` matches `hermes_wiki/plugin.yaml`.
2. Run the test suite.
3. Build the wheel and source distribution.
4. Inspect the wheel for plugin assets.
5. Test installation from GitHub into a clean environment.
6. Test installation into the Hermes runtime Python.
7. Enable the plugin and verify runtime discovery.
8. Tag the release and publish to PyPI when ready.

Example commands:

```bash
python3 -m pytest
uv build
python3 -m zipfile -l dist/hermes_wiki-0.1.0-py3-none-any.whl
```

The wheel should include at least:

```text
hermes_wiki/__init__.py
hermes_wiki/plugin.yaml
hermes_wiki/requirements.txt
hermes_wiki/skills/wiki-operator/SKILL.md
hermes_wiki-0.1.0.dist-info/entry_points.txt
```

Clean GitHub install test:

```bash
uv venv /tmp/hermes-wiki-pip-test
uv pip install --python /tmp/hermes-wiki-pip-test/bin/python git+https://github.com/zombiearnie88/hermes-wiki.git
/tmp/hermes-wiki-pip-test/bin/python -c "import hermes_wiki; assert callable(hermes_wiki.register)"
/tmp/hermes-wiki-pip-test/bin/hermes-wiki --help
```

Hermes runtime install test:

```bash
uv pip install --python /opt/hermes/.venv/bin/python git+https://github.com/zombiearnie88/hermes-wiki.git
/opt/hermes/.venv/bin/hermes plugins enable hermes-wiki
HERMES_PLUGINS_DEBUG=1 /opt/hermes/.venv/bin/hermes plugins list
```

## GitHub Version Pinning

For development installs, use the default branch:

```bash
uv pip install --python /opt/hermes/.venv/bin/python git+https://github.com/zombiearnie88/hermes-wiki.git
```

For reproducible deployment, pin a tag:

```bash
uv pip install --python /opt/hermes/.venv/bin/python git+https://github.com/zombiearnie88/hermes-wiki.git@v0.1.0
```

Create tags from clean release commits:

```bash
git tag v0.1.0
git push origin v0.1.0
```

## PyPI Publishing

After the GitHub install path is validated, publish to PyPI so users can install without Git:

```bash
uv build
uv publish
```

Users can then install with:

```bash
uv pip install --python /opt/hermes/.venv/bin/python hermes-wiki
```

If using Twine instead of `uv publish`:

```bash
python3 -m pip install twine
python3 -m twine check dist/*
python3 -m twine upload dist/*
```

## Fresh Docker Example

Use `examples/docker-compose.pip.yml` to validate the pip/GitHub distribution path without reusing repo-local Docker profiles, auth, or mounted source code.

Start the example:

```bash
docker compose -f examples/docker-compose.pip.yml up -d
```

Pin a tag instead of installing the default branch:

```bash
HERMES_WIKI_PACKAGE='git+https://github.com/zombiearnie88/hermes-wiki.git@v0.1.0' \
  docker compose -f examples/docker-compose.pip.yml up -d
```

Reset all example state:

```bash
docker compose -f examples/docker-compose.pip.yml down -v
```

## Verification Checklist

1. `hermes plugins list` shows `hermes-wiki` as enabled.
2. Runtime plugin discovery reports no import error.
3. `wiki_status` works from the Hermes tool or slash-command surface.
4. `hermes-wiki --help` works in a clean pip-installed environment.
5. The wheel contains `plugin.yaml`, `requirements.txt`, and bundled skill files.
6. Docker example starts from empty named volumes and does not use `docker/data/`.

## Future Improvements

Consider splitting heavy dependencies into extras after the first public release:

```toml
[project.optional-dependencies]
pdf = ["pymupdf"]
office = ["markitdown[all]"]
all = ["json-repair", "pymupdf", "markitdown[all]"]
```

Keep the initial release simple unless dependency size becomes a real deployment problem.
