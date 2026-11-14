"""
Renders the example schemes before each build, so every diagram in the docs
is drawn by the code being documented.

For each beam in each `examples/*.yaml`, writes `<file>-<beam>.png`, `.svg`
and `.pdf` to `beamz_gallery_output`. Pages show them with the `beam-figure`
directive:

    ```{beam-figure} gallery.yaml simple_udl
    A simply supported beam.
    ```
"""

from __future__ import annotations

import pathlib

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective

logger = logging.getLogger(__name__)


def render_examples(app) -> None:
    import beamz9000 as bz

    src = pathlib.Path(app.config.beamz_gallery_examples)
    out = pathlib.Path(app.config.beamz_gallery_output)
    out.mkdir(parents=True, exist_ok=True)
    png = bz.MatplotlibRenderer(width=10, dpi=160)
    count = 0
    for path in sorted(src.glob("*.yaml")):
        for beam_id, beam in bz.load_scheme(path):
            diagram = bz.beam_diagram(beam, beam_id=beam_id)
            stem = out / f"{path.stem}-{beam_id}"
            png.save(diagram, stem.with_suffix(".png"))
            bz.MatplotlibRenderer().save(diagram, stem.with_suffix(".pdf"))
            bz.SVGRenderer().save(diagram, stem.with_suffix(".svg"))
            count += 1
    logger.info(f"beamz_gallery: rendered {count} beams from {src}")


class BeamFigure(SphinxDirective):
    """A rendered example beam, with download links for each format."""

    required_arguments = 2  # scheme file name, beam id
    has_content = True
    option_spec = {"alt": directives.unchanged, "no-downloads": directives.flag}

    def run(self):
        scheme, beam_id = self.arguments
        stem = pathlib.Path(scheme).stem
        out = pathlib.Path(self.config.beamz_gallery_output)
        docdir = pathlib.Path(self.env.doc2path(self.env.docname)).parent
        rel = pathlib.Path(*[".."] * len(docdir.relative_to(self.env.srcdir).parts), out.relative_to(self.env.srcdir))

        figure = nodes.figure(classes=["beam-figure"])
        uri = (rel / f"{stem}-{beam_id}.png").as_posix()
        image = nodes.image(uri=uri, alt=self.options.get("alt", f"Free-body diagram of {beam_id}"))
        figure += image
        if self.content:
            caption = nodes.caption()
            self.state.nested_parse(self.content, self.content_offset, caption)
            # Unwrap the paragraph so the caption holds inline text.
            if len(caption) == 1 and isinstance(caption[0], nodes.paragraph):
                caption.children = caption[0].children
            figure += caption
        result = [figure]
        if "no-downloads" not in self.options:
            para = nodes.paragraph(classes=["beam-downloads"])
            for i, fmt in enumerate(["svg", "pdf", "png"]):
                if i:
                    para += nodes.Text(" · ")
                from sphinx import addnodes

                ref = addnodes.download_reference(
                    "", "", refdoc=self.env.docname, reftarget="/" + (out.relative_to(self.env.srcdir) / f"{stem}-{beam_id}.{fmt}").as_posix(),
                    refexplicit=True,
                )
                ref += nodes.literal(fmt.upper(), fmt.upper())
                para += ref
            result.append(para)
        return result


def setup(app):
    app.add_config_value("beamz_gallery_examples", "examples", "env")
    app.add_config_value("beamz_gallery_output", "_generated", "env")
    app.connect("builder-inited", render_examples)
    app.add_directive("beam-figure", BeamFigure)
    return {"version": "0.1", "parallel_read_safe": True, "parallel_write_safe": True}
