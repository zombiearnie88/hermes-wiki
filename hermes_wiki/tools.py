from __future__ import annotations

import json

from .commands import (
    _resolve_workspace,
    _run_add,
    _run_add_async,
    _run_deps,
    _run_config,
    _run_init,
    _run_list,
    _run_status,
    is_failure_output,
)
from .config import DEFAULT_CONFIG
from .pageindex.config import load_pageindex_config
from .pageindex.retrieve import (
    PageRangeError,
    get_document_structure as _get_pageindex_structure,
    get_page_content as _get_pageindex_content,
)
from .workspace import workspace_paths


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
    domain = args.get("domain") or None
    long_doc_threshold = args.get("long_doc_threshold")
    if long_doc_threshold is None:
        long_doc_threshold = DEFAULT_CONFIG["long_doc_threshold"]

    try:
        output = _run_init(path, model, language, int(long_doc_threshold), provider=provider, domain=domain)
    except Exception as exc:
        return _failure("wiki_init", str(exc), path=path, domain=domain)
    return _wrap_output("wiki_init", output, path=path, domain=domain)


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


async def wiki_add_async(args: dict, *, llm, **kwargs) -> str:
    del kwargs
    path = args.get("path")
    workspace = args.get("workspace") or None
    model = args.get("model") or None
    provider = args.get("provider") or None
    language = args.get("language") or None

    if not path:
        return _failure("wiki_add", "Missing required argument: path")

    try:
        output = await _run_add_async(path, workspace, model, language, provider, llm=llm)
    except Exception as exc:
        return _failure("wiki_add", str(exc), path=path, workspace=workspace, model=model, provider=provider)
    return _wrap_output("wiki_add", output, path=path, workspace=workspace, model=model, provider=provider)


def wiki_status(args: dict, **kwargs) -> str:
    workspace = args.get("workspace") or None
    plugin_llm_available = bool(kwargs.get("plugin_llm_available", False))

    try:
        output = _run_status(workspace, plugin_llm_available=plugin_llm_available)
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
    concept_generation_concurrency = args.get("concept_generation_concurrency")

    try:
        output = _run_config(
            workspace,
            model=model,
            provider=provider,
            language=language,
            long_doc_threshold=long_doc_threshold,
            concept_generation_concurrency=concept_generation_concurrency,
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
    install = args.get("install") or None
    plugin_llm_available = bool(kwargs.get("plugin_llm_available", False))

    try:
        output = _run_deps(install, plugin_llm_available=plugin_llm_available)
    except Exception as exc:
        return _failure("wiki_deps", str(exc), install=install)
    return _wrap_output("wiki_deps", output, install=install)


def _resolve_tool_paths(action: str, workspace: str | None):
    workspace_root, error = _resolve_workspace(workspace)
    if error:
        return None, _failure(action, error, workspace=workspace)
    return workspace_paths(workspace_root), None


def get_document_structure(args: dict, **kwargs) -> str:
    del kwargs
    action = "get_document_structure"
    doc_name = args.get("doc_name")
    workspace = args.get("workspace") or None
    if not doc_name:
        return _failure(action, "Missing required argument: doc_name", workspace=workspace)

    paths, error = _resolve_tool_paths(action, workspace)
    if error:
        return error
    try:
        payload = _get_pageindex_structure(paths, str(doc_name))
    except FileNotFoundError as exc:
        return _failure(action, str(exc), doc_name=doc_name, workspace=workspace)
    except Exception as exc:
        return _failure(action, str(exc), doc_name=doc_name, workspace=workspace)
    return _success(action, "document structure loaded", **payload, workspace=workspace)


def get_page_content(args: dict, **kwargs) -> str:
    del kwargs
    action = "get_page_content"
    doc_name = args.get("doc_name")
    pages = args.get("pages")
    workspace = args.get("workspace") or None
    if not doc_name:
        return _failure(action, "Missing required argument: doc_name", workspace=workspace)
    if not pages:
        return _failure(action, "Missing required argument: pages", doc_name=doc_name, workspace=workspace)

    paths, error = _resolve_tool_paths(action, workspace)
    if error:
        return error
    try:
        config = load_pageindex_config(paths.config_path)
        payload = _get_pageindex_content(
            paths,
            str(doc_name),
            str(pages),
            max_pages=config.max_pages_per_tool_call,
        )
    except (FileNotFoundError, PageRangeError) as exc:
        return _failure(action, str(exc), doc_name=doc_name, pages=pages, workspace=workspace)
    except Exception as exc:
        return _failure(action, str(exc), doc_name=doc_name, pages=pages, workspace=workspace)
    return _success(action, "page content loaded", **payload, workspace=workspace)
