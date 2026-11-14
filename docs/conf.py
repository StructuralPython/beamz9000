"""Sphinx configuration for the beamz9000 documentation."""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE / "_ext"))

import beamz9000  # noqa: E402

project = "beamz9000"
author = "Connor Ferster"
copyright = "2026, StructuralPython"
release = beamz9000.__version__
version = release

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx.ext.viewcode",
    "sphinxcontrib.autodoc_pydantic",
    "sphinx_copybutton",
    "sphinx_design",
    "beamz_gallery",
]

myst_enable_extensions = ["colon_fence", "deflist", "fieldlist", "attrs_inline", "attrs_block"]
myst_heading_anchors = 3

# Docstrings write `name` for code, as in Markdown.
default_role = "code"

exclude_patterns = ["_build", "_generated/*.yaml", "Thumbs.db", ".DS_Store"]

# --- autodoc ---------------------------------------------------------------------------
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_default_options = {"members": True, "show-inheritance": False}
autodoc_pydantic_model_show_json = False
autodoc_pydantic_model_show_config_summary = False
autodoc_pydantic_model_show_validator_summary = False
autodoc_pydantic_model_show_validator_members = False
autodoc_pydantic_model_show_field_summary = True
autodoc_pydantic_field_list_validators = False
autodoc_pydantic_model_member_order = "bysource"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "shapely": ("https://shapely.readthedocs.io/en/stable/", None),
    "matplotlib": ("https://matplotlib.org/stable/", None),
    "pydantic": ("https://pydantic.dev/docs/validation/latest/", None),
}

# --- gallery ---------------------------------------------------------------------------
beamz_gallery_examples = str(ROOT / "examples")
beamz_gallery_output = str(HERE / "_generated")

# --- HTML ------------------------------------------------------------------------------
html_theme = "shibuya"
html_title = "beamz9000"
html_baseurl = "https://beamz9000.structuralpython.com/"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_favicon = "_static/favicon.svg"
html_logo = "_static/logo.svg"
html_copy_source = False
html_show_sourcelink = False

html_context = {
    "source_type": "github",
    "source_user": "StructuralPython",
    "source_repo": "beamz9000",
    "source_version": "main",
    "source_docs_path": "/docs/",
}

html_theme_options = {
    "accent_color": "blue",
    "github_url": "https://github.com/StructuralPython/beamz9000",
    "nav_links": [
        {"title": "Get started", "url": "getting-started"},
        {"title": "Scheme format", "url": "scheme"},
        {"title": "Gallery", "url": "gallery"},
        {"title": "API", "url": "api/index"},
    ],
    "show_ai_links": False,
}
