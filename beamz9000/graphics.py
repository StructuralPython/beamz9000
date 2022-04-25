from matplotlib.path import Path
import matplotlib.patches as patches
import matplotlib.transforms as transforms
import matplotlib.axes as axes


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
    # translate_transform.translate(offset_x, offset_y)
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


def get_anchor_point(path_patch: patches.PathPatch, location: str) -> tuple[float, float]:
    """
    Returns an x, y tuple representing the anchor point described in 'location'.
    'location': a string that is two of the following words separated by a space.
        "top", "bottom", "left", "right", "center"
        e.g. "top left", "right bottom", "center center", "center right"
    """
    bbox = path_patch.get_extents()
    xmin, ymin, xmax, ymax = bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax
    # print(xmin, ymin, xmax, ymax)

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









