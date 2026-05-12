from __future__ import annotations


WIKI_INIT = {
    "name": "wiki_init",
    "description": (
        "Initialize a Hermes wiki workspace with raw/, wiki/, and .hermeskb/. "
        "Use this when the user wants to create a new wiki workspace or set its initial model, provider, language, or long-doc threshold."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Workspace root path to initialize. Defaults to the current directory.",
            },
            "model": {
                "type": "string",
                "description": "Default Hermes model to store in the workspace config.",
            },
            "provider": {
                "type": "string",
                "description": "Default Hermes provider to store in the workspace config.",
            },
            "language": {
                "type": "string",
                "description": "Default output language to store in the workspace config.",
            },
            "long_doc_threshold": {
                "type": "integer",
                "description": "Page-count threshold where PDFs are treated as unsupported long documents.",
            },
        },
    },
}


WIKI_ADD = {
    "name": "wiki_add",
    "description": (
        "Ingest a source file or directory into a Hermes wiki workspace. "
        "Use this for supported markdown, text, CSV, PDF, and MarkItDown-backed formats when the user wants summaries and concept pages created or updated. "
        "Uses the workspace config model and provider unless explicit one-off overrides are supplied."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "File or directory path to ingest.",
            },
            "workspace": {
                "type": "string",
                "description": "Optional workspace root or nested path inside the workspace.",
            },
            "model": {
                "type": "string",
                "description": "Optional one-off model override for this ingest run. Defaults to the workspace config model.",
            },
            "provider": {
                "type": "string",
                "description": "Optional one-off provider override for this ingest run. Defaults to the workspace config provider.",
            },
            "language": {
                "type": "string",
                "description": "Optional one-off language override for this ingest run.",
            },
        },
        "required": ["path"],
    },
}


WIKI_STATUS = {
    "name": "wiki_status",
    "description": (
        "Show Hermes wiki workspace status, dependency health, and capability readiness. "
        "Use this when the user wants to inspect the current workspace or confirm whether ingest and generation are available."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "workspace": {
                "type": "string",
                "description": "Optional workspace root or nested path inside the workspace.",
            },
        },
    },
}


WIKI_CONFIG = {
    "name": "wiki_config",
    "description": (
        "Show or update a Hermes wiki workspace configuration. "
        "Use this when the user wants to inspect or change the stored default model, provider, language, or long-doc threshold."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "workspace": {
                "type": "string",
                "description": "Optional workspace root or nested path inside the workspace.",
            },
            "model": {
                "type": "string",
                "description": "New default Hermes model to persist in the workspace config.",
            },
            "provider": {
                "type": "string",
                "description": "New default Hermes provider to persist in the workspace config.",
            },
            "language": {
                "type": "string",
                "description": "New default output language to persist in the workspace config.",
            },
            "long_doc_threshold": {
                "type": "integer",
                "description": "New page-count threshold for unsupported long PDFs.",
            },
        },
    },
}


WIKI_LIST = {
    "name": "wiki_list",
    "description": (
        "List Hermes wiki documents and concept pages tracked in a workspace. "
        "Use this when the user wants to inspect what has already been ingested and which concept pages exist."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "workspace": {
                "type": "string",
                "description": "Optional workspace root or nested path inside the workspace.",
            },
        },
    },
}


WIKI_DEPS = {
    "name": "wiki_deps",
    "description": (
        "Inspect Hermes wiki runtime dependency health and optionally install missing dependency groups. "
        "Use this when wiki capabilities are blocked by missing json-repair, PyMuPDF, or MarkItDown."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "install": {
                "type": "string",
                "enum": ["core", "pdf", "office", "all"],
                "description": "Optional dependency group to install into the active Hermes runtime.",
            },
        },
    },
}
