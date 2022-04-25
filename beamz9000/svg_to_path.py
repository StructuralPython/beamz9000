
import pathlib
import re
import numpy as np
from matplotlib.path import Path
from matplotlib.patches import PathPatch
import svgpathtools as svg


def load_svg_file(svg_filepath: pathlib.Path) -> list[Path]:
    """
    Returns a list of matplotlib.path.Path objects extracted from path data
    contained in the SVG file of 'svg_filepath'.
    """
    mpl_paths = []
    paths, _attributes = svg.svg2paths(str(svg_filepath), convert_circles_to_paths=True)
    for path in paths:
        mpl_paths.append(
                svg_path_parse(path.d())
            )
    return PathPatch(Path.make_compound_path(*mpl_paths))


def svg_path_parse(svg_path: str):
    """
    Returns a matplotlib.path.Path object for an SVG path string describing
    a single path.

    Based on code from:
    https://matplotlib.org/stable/gallery/showcase/firefox.html#sphx-glr-gallery-showcase-firefox-py
    """
    commands = {'M': (Path.MOVETO,),
                'L': (Path.LINETO,),
                'Q': (Path.CURVE3,)*2,
                'C': (Path.CURVE4,)*3,
                'Z': (Path.CLOSEPOLY,)}
    vertices = []
    codes = []
    svg_path = svg_path.replace(" ", ",")
    cmd_values = re.split("([A-Za-z])", svg_path)[1:]  # Split over commands.
    for cmd, values in zip(cmd_values[::2], cmd_values[1::2]):
        # Numbers are separated either by commas, or by +/- signs (but not at
        # the beginning of the string).
        if values:
            points = [float(value) for value in re.split(r",|\s", values) if value]
            if len(points) > 2:
                points = list(zip(points[::2], points[1::2]))
        else:
            points = [(0., 0.)]

        if cmd.islower() and cmd != 'm':
            points += vertices[-1][-1]
        codes.extend(commands[cmd.upper()])
        vertices.append(
            np.reshape(
                np.array(points), 
                (-1, 2)
            )
        )
    codes_array = np.array(codes)
    vertices_array = np.concatenate(vertices)
    return Path(vertices_array, codes_array)
