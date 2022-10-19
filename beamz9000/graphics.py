from typing import Any
import math
from matplotlib.path import Path
import matplotlib.patches as patches
import matplotlib.transforms as transforms
import matplotlib.axes as axes
import numpy as np



def get_svg_size(ax: axes.Axes, path_patch: patches.PathPatch):
    """
    Returns the depth (y-dimension) of 'path_patch' when transformed into
    the data-space coordinate system in 'ax'.
    """
    ymin = get_extent(path_patch, "y", "min")
    ymax = get_extent(path_patch, "y", "max")
    xmin = get_extent(path_patch, "x", "min")
    xmax = get_extent(path_patch, "x", "max")
    x_min_data, y_min_data = ax.transData.inverted().transform([xmin, ymin])
    x_max_data, y_max_data = ax.transData.inverted().transform([xmax, ymax])
    y_range = abs(y_max_data - y_min_data)
    x_range = abs(x_max_data - x_min_data)
    return x_range, y_range


def get_svg_translation_transform(
    ax: axes.Axes = None, 
    path_patch: patches.PathPatch = None,
    target: tuple[float, float] = None,
    anchor_location: str = None,
    scale_factor: float = None,
    ) -> transforms.Transform:
    """
    Returns a matplotlib.transform.Transform to translate the 'path_patch' so that its 'anchor_location'
    (a designated point on/within the path patch's bounding box) is aligned to 'target', a point within the 
    data space of 'axes'.

    axes: a matplotlib axes object
    path_patch: a matplotlib PathPatch object
    target: an x, y tuple of coordinates within the data space of 'axes'
    anchor_location: a string that is two of the following words separated by a space.
        "top", "bottom", "left", "right", "center"
        e.g. "top left", "right bottom", "center center", "center right"
    """
    svg_flip = get_svg_flip_transform()
    path_patch.set_transform(svg_flip)
    svg_anchor_x, svg_anchor_y = get_anchor_point(path_patch, anchor_location)
    target_x, target_y = target
    anchor_to_origin = transforms.Affine2D()
    anchor_to_origin_transform = anchor_to_origin.translate(-svg_anchor_x, -svg_anchor_y)
    scale_transform = get_scale_transform(scale_factor)
    translate_transform = transforms.ScaledTranslation(target_x, target_y, ax.transData)
    return svg_flip + anchor_to_origin_transform + scale_transform + translate_transform


def get_svg_flip_transform() -> transforms.Transform:
    """
    Returns a matplotlib.transform.Transform that is required to place all SVG objects
    into the plot of the data space in the correct orientation (SVG coordinate
    systems are "upside-down").
    """
    flip = transforms.Affine2D()
    flip.scale(1, -1)
    return flip


def get_scale_transform(scale_factor: float) -> transforms.Transform():
    """
    Returns a scale transform set to scale the patch by 'scale_factor'
    """
    scale = transforms.Affine2D()
    scale.scale(scale_factor)
    return scale


def get_extent(patch: patches.Patch, axis: str, extent: str) -> float:
    """
    patch: a patch
    axis: a string, either "x" or "y"
    extent: a string, either "min" or "max"
    """
    bbox = patch.get_extents()
    extents = {
        "xmin": bbox.xmin,
        "ymin": bbox.ymin,
        "xmax": bbox.xmax,
        "ymax": bbox.ymax,
    }
    return extents[f"{axis}{extent}"]


def get_anchor_point(path_patch: patches.PathPatch, location: str) -> tuple[float, float]:
    """
    Returns an x, y tuple representing the anchor point described in 'location'.
    'location': a string that is two of the following words separated by a space.
        "top", "bottom", "left", "right", "center"
        e.g. "top left", "right bottom", "center center", "center right"
    """
    bbox = path_patch.get_extents()
    xmin, ymin, xmax, ymax = bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax

    if len(location.split()) != 2:
        raise ValueError(
            "'location' must be a string containing two words, separated by a space, describing a "
            "location relative to a bounding box, e.g. 'top left', 'bottom right', 'center right', 'bottom center'.\n"
            "Each word must be one of:\n'top', 'bottom', 'left', 'right', 'center'.\n"
            f"{location} was passed instead."
        )
    location = location.lower()
    if "center" in location:
        x = (xmax + xmin) / 2
        y = (ymax + ymin) / 2

    if "right" in location:
        x = xmax
    elif "left" in location:
        x = xmin
    elif "top" in location:
        y = ymax
    elif "bottom" in location:
        y = ymin
    return x, y


def arrow_at_coordinate(point: tuple, magnitude: float, angle: float, color, **params: dict):
    """
    Returns ax with an arrow added to it that *points to* the coordinate ('x', 'y') with
    an arrow containing arrow_params.
    """
    pt_x, pt_y = point
    v_x, v_y = math.cos(math.radians(90 - angle)), math.sin(math.radians(90 - angle))
    dx = -v_x * magnitude
    dy = -v_y * magnitude
    x = pt_x - dx
    y = pt_y - dy
    params['edgecolor'] = color
    params['facecolor'] = color
    arrow = patches.FancyArrow(
        x=x, 
        y=y, 
        dx=dx, 
        dy=dy, 
        length_includes_head=True,
        head_width=magnitude / 10,
        head_length=magnitude / 6,
        **params)
    return arrow


def distributed_load_region(
    beam_length: float,
    start_magnitude: float, 
    start_loc: tuple[float], 
    end_magnitude: float, 
    end_loc: tuple[float],
    top_of_beam: float,
    color: Any,
    **params: dict,
    ):
    """
    Returns a distributed load polygon patch and arrow patches
    """
    N_ARROWS = 7
    region = end_loc - start_loc
    n_arrows = N_ARROWS
    if region / beam_length < 0.50:
        n_arrows = 5
    elif region / beam_length < 0.20:
        n_arrows = 3
    elif region / beam_length < 0.10:
        n_arrows = 2

    xy = np.array(
        [
            [start_loc, top_of_beam],
            [start_loc, start_magnitude],
            [end_loc, end_magnitude],
            [end_loc, top_of_beam]
        ]
    )
    params = {"edgecolor": color, "facecolor": color, "alpha": 0.5}
    distributed_patch = patches.Polygon(xy=xy, closed=True, **params)
    arrows = []
    x_interval = region / (n_arrows - 1)
    for arrow_idx in range(n_arrows):
        x_coord = arrow_idx * x_interval + start_loc
        arrow_magnitude = (end_magnitude - start_magnitude) / region * (x_coord - start_magnitude) + start_magnitude
        arrow = arrow_at_coordinate(point=(x_coord, top_of_beam), magnitude=arrow_magnitude, angle=0, color=color, **params)
        arrows.append(arrow)

    return distributed_patch, arrows


