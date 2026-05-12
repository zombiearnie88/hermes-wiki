from __future__ import annotations

import json

from .commands import (
    _run_add,
    _run_deps,
    _run_config,
    _run_init,
    _run_list,
    _run_status,
    is_failure_output,
)
from .config import DEFAULT_CONFIG


def _success(action: str, output: str, **extra) -> str:
    payload = {"ok": True, "action": action, "output": output}
    payload.update({key: value for key, value in extra.items() if value is not None})
    return json.dumps(payload)


def _failure(action: str, error: str, **extra) -> str:
    payload = {"ok": False, "action": action, "error": error}
    payload.update({key: value for key, value in extra.items() if value is not None})
    return json.dumps(payload)


def _wrap_output(action: str, output: str, **extra) -> str:
    if is_failure_output(output):
        return _failure(action, output, **extra)
    return _success(action, output, **extra)


def wiki_init(args: dict, **kwargs) -> str:
    del kwargs
    path = args.get("path") or "."
    model = args.get("model") or DEFAULT_CONFIG["model"]
    provider = args.get("provider") or DEFAULT_CONFIG["provider"]
    language = args.get("language") or DEFAULT_CONFIG["language"]
    long_doc_threshold = args.get("long_doc_threshold")
    if long_doc_threshold is None:
        long_doc_threshold = DEFAULT_CONFIG["long_doc_threshold"]

    try:
        output = _run_init(path, model, language, int(long_doc_threshold), provider=provider)
    except Exception as exc:
        return _failure("wiki_init", str(exc), path=path)
    return _wrap_output("wiki_init", output, path=path)


def wiki_add(args: dict, **kwargs) -> str:
    del kwargs
    path = args.get("path")
    workspace = args.get("workspace") or None
    model = args.get("model") or None
    provider = args.get("provider") or None
    language = args.get("language") or None

    if not path:
        return _failure("wiki_add", "Missing required argument: path")

    try:
        output = _run_add(path, workspace, model, language, provider)
    except Exception as exc:
        return _failure("wiki_add", str(exc), path=path, workspace=workspace, model=model, provider=provider)
    return _wrap_output("wiki_add", output, path=path, workspace=workspace, model=model, provider=provider)


def wiki_status(args: dict, **kwargs) -> str:
    del kwargs
    workspace = args.get("workspace") or None

    try:
        output = _run_status(workspace)
    except Exception as exc:
        return _failure("wiki_status", str(exc), workspace=workspace)
    return _wrap_output("wiki_status", output, workspace=workspace)


def wiki_config(args: dict, **kwargs) -> str:
    del kwargs
    workspace = args.get("workspace") or None
    model = args.get("model") or None
    provider = args.get("provider") or None
    language = args.get("language") or None
    long_doc_threshold = args.get("long_doc_threshold")

    try:
        output = _run_config(
            workspace,
            model=model,
            provider=provider,
            language=language,
            long_doc_threshold=long_doc_threshold,
        )
    except Exception as exc:
        return _failure("wiki_config", str(exc), workspace=workspace)
    return _wrap_output("wiki_config", output, workspace=workspace)


def wiki_list(args: dict, **kwargs) -> str:
    del kwargs
    workspace = args.get("workspace") or None

    try:
        output = _run_list(workspace)
    except Exception as exc:
        return _failure("wiki_list", str(exc), workspace=workspace)
    return _wrap_output("wiki_list", output, workspace=workspace)


def wiki_deps(args: dict, **kwargs) -> str:
    del kwargs
    install = args.get("install") or None

    try:
        output = _run_deps(install)
    except Exception as exc:
        return _failure("wiki_deps", str(exc), install=install)
    return _wrap_output("wiki_deps", output, install=install)
