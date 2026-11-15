"""Analysis results and models in a ymprint document's variables, and exporting them."""

import json
import pathlib

import pytest

import beamz9000 as bz
from beamz9000 import analysis
from beamz9000.results import results_dict

pytest.importorskip("ymprint")
pytest.importorskip("pycba_tools")
pymupdf = pytest.importorskip("pymupdf")

EXAMPLES = pathlib.Path(__file__).parents[1] / "examples"
PAGE = {"frames": {"all_pages": {"width": 400, "height": 600}}}


def _factored():
    beam = bz.load_scheme(EXAMPLES / "analysis.yaml")["factored_floor_beam"]
    return beam, analysis.analyze(beam, list(beam.results.diagrams))


def test_results_dict_is_in_the_schemes_units():
    beam, result = _factored()
    d = results_dict(beam, result)
    assert d["engine"] == "pycba"
    assert d["units"] == {"force": "kN", "moment": "kN·m", "deflection": "mm", "rotation": "rad", "x": "m"}
    assert d["cases"] == ["D", "L"]
    assert d["combos"] == {"forces": ["ULS1", "ULS2", "ULS3"], "deflections": ["SLS"]}
    a = d["reactions"]["A"]
    assert a["ULS2"]["Fy"] == pytest.approx(1.25 * a["D"]["Fy"] + 1.5 * a["L"]["Fy"], rel=1e-5)
    assert a["max"]["Fy"] == max(a[c]["Fy"] for c in ("ULS1", "ULS2", "ULS3"))
    # With force combinations, moment lists each combination and their envelope.
    assert set(d["moment"]) == {"ULS1", "ULS2", "ULS3", "envelope"}
    env = d["moment"]["envelope"]
    assert env["max"] == max(d["moment"][c]["max"] for c in ("ULS1", "ULS2", "ULS3"))
    assert 0 <= env["x_max"] <= 12.6
    assert set(d["deflection"]) == {"SLS", "envelope"}
    assert type(d["model"]).__name__ == "CBAModel"
    # Everything but the model is plain JSON.
    json.dumps({k: v for k, v in d.items() if k != "model"})


def test_results_dict_without_units_or_labels():
    beam = bz.parse_scheme({"B": {"spans": [4.0], "loads": [{"dist": {"w": 2.0}}], "results": ["moment", "reactions"]}})["B"]
    d = results_dict(beam, analysis.analyze(beam, ["moment"]))
    assert d["units"] is None
    assert d["cases"] == ["uncased"]
    assert d["reactions"]["N0"]["uncased"]["Fy"] == pytest.approx(4.0)
    assert d["moment"]["uncased"]["max"] == pytest.approx(4.0, rel=1e-4)  # wL²/8, sagging positive
    assert d["moment"]["uncased"]["x_max"] == pytest.approx(2.0, abs=0.02)  # Nearest station.


def test_block_puts_results_under_the_beam_id(tmp_path):
    from beamz9000.ymprint import beam_block

    (tmp_path / "analysis.yaml").write_text((EXAMPLES / "analysis.yaml").read_text())
    context = {**PAGE, "base_dir": str(tmp_path), "vars": {}}
    beam_block("_beam", {"scheme": "analysis.yaml", "beam": "factored_floor_beam"}, context)
    beam_block("_beam_c", {"scheme": "analysis.yaml", "beam": "cantilever", "namespace": "cant"}, context)
    assert set(context["vars"]) == {"factored_floor_beam", "cant"}
    assert context["vars"]["cant"]["reactions"]["A"]["D"]["Fy"] == pytest.approx(12.0)
    assert type(context["vars"]["factored_floor_beam"]["model"]).__name__ == "CBAModel"


def test_block_without_results_adds_nothing(tmp_path):
    from beamz9000.ymprint import beam_block

    context = {**PAGE, "base_dir": str(tmp_path), "vars": {}}
    beam_block("_beam_b", {"beam": {"spans": ["3 m"], "loads": [{"dist": {"w": "2 kN/m"}}]}}, context)
    assert context["vars"] == {}


def test_results_are_usable_in_the_document(tmp_path):
    from beamz9000.ymprint import app

    (tmp_path / "analysis.yaml").write_text((EXAMPLES / "analysis.yaml").read_text())
    doc = {"Beam": [
        {"_beam": {"scheme": "analysis.yaml", "beam": "factored_floor_beam", "namespace": "fb"}},
        "Max reaction at B: {{ fb.reactions.B.max.Fy | round(1) }} {{ fb.units.force }}",
    ]}
    src = tmp_path / "doc.yaml"
    import yaml
    src.write_text(yaml.safe_dump(doc, allow_unicode=True))
    out = tmp_path / "out.pdf"
    app.render(src, out, base_dir=tmp_path, discover_config=False)
    text = "".join(p.get_text() for p in pymupdf.open(out))
    assert "Max reaction at B: 108.6 kN" in text


@pytest.mark.parametrize("engine", ["pycba", "pynite"])
def test_models_export_with_metadata_and_read_back(engine):
    pytest.importorskip(f"{engine}_tools")
    from ymprint import exports
    from ymprint.plugins import load_plugins

    load_plugins()  # Runs beamz9000's setup through its entry point.
    beam = bz.load_scheme(EXAMPLES / "analysis.yaml")["floor_beam"]
    model = analysis.analyze(beam, ["moment"], engine).model
    data = json.loads(exports.dumps({"model": model}))["model"]
    library = {"pycba": "pycba", "pynite": "Pynite"}[engine]
    assert data["metadata"]["library"] == library
    assert data["metadata"]["generator"] == f"{engine}-tools"
    assert data["metadata"]["library_version"] and data["metadata"]["generator_version"]
    back = json.loads(exports.dumps({"model": model}), object_hook=exports.decode_typed)["model"]
    assert type(back) is type(model)


def test_the_model_exports_by_path(tmp_path):
    from ymprint import exports
    from ymprint.plugins import load_plugins

    from beamz9000.ymprint import beam_block

    load_plugins()
    (tmp_path / "analysis.yaml").write_text((EXAMPLES / "analysis.yaml").read_text())
    context = {**PAGE, "base_dir": str(tmp_path), "vars": {}}
    beam_block("_beam", {"scheme": "analysis.yaml", "beam": "factored_floor_beam", "namespace": "fb"}, context)
    values = exports.evaluate_exports(
        {"model": "$fb.model", "Fy": "$fb.reactions.B.max.Fy"}, context["vars"], "calc.yml")
    data = json.loads(exports.dumps(values))
    assert data["model"]["metadata"]["generator"] == "pycba-tools"
    assert data["Fy"] == pytest.approx(108.56)
