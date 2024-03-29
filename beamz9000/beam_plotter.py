from typing import Union, Optional
import matplotlib.pyplot as plt
from matplotlib.path import Path
from matplotlib.patches import PathPatch
import matplotlib as mpl
import numpy as np
import pathlib
from beamz9000.model import Label, Node, Support, Fixity, Joint, Beam, Load
import beamz9000.graphics as graphics
import beamz9000.svg_to_path as svg_to_path
import copy

    # H_ROLLER = 0
    # V_ROLLER = 1
    # PINNED = 2
    # FIXED = 3
    # H_SPRING = 4
    # V_SPRING = 5
    # M_SPRING = 6
    # T_SPRING = 7

class BeamPlotter:
    """
    A class that plots the data in 'beam'
    """
    def __init__(self, beam: Beam):
        self.beam = beam
        self.style = 'default'
        self.support_svgs = {
            0: pathlib.Path(__file__).parent / self.style / "svg_supports"  / "H_ROLLER.svg",
            1: pathlib.Path(__file__).parent / self.style / "svg_supports"  / "V_ROLLER.svg",
            2: pathlib.Path(__file__).parent / self.style / "svg_supports"  / "PINNED.svg",
            3: pathlib.Path(__file__).parent / self.style / "svg_supports"  / "FIXED.svg",
            4: pathlib.Path(__file__).parent / self.style / "svg_supports"  / "H_SPRING.svg",
            5: pathlib.Path(__file__).parent / self.style / "svg_supports"  / "V_SPRING.svg",
            6: pathlib.Path(__file__).parent / self.style / "svg_supports"  / "M_SPRING.svg",
            7: pathlib.Path(__file__).parent / self.style / "svg_supports"  / "T_SPRING.svg",
        }
        self.misc_svgs = {
            "DIM_TICKS": pathlib.Path(__file__).parent / self.style / "misc"  / "DIM_TICK.svg",
        }
        self.strata = {
            "max_load_depth": self.beam.depth * 4/3 or self.beam.length / 10,
            "beam_top": self.beam.depth / 2,
            "beam_bottom": -self.beam.depth / 2,
            "gap": self.beam.depth * 0.05,
            "support_depth": self.beam.depth / 2,
            "ground_depth": self.beam.depth / 4,
            "displacement_depth": self.beam.depth * 2/3,
            "dimension_depth": self.beam.depth / 2,
        }
        

    def plot(self, style='default', **kwargs):
        fig, ax = self.init_plot()
        fig, ax = self.add_beam_plot(fig, ax, **kwargs)
        fig, ax = self.add_loads(fig, ax, **kwargs)
        fig, ax = self.add_beam_supports(fig, ax, **kwargs)
        fig, ax = self.add_node_labels(fig, ax, **kwargs)
        fig, ax = self.add_dimensions(fig, ax, y_offset=-2, **kwargs)
        return fig, ax

    
    def init_plot(self, **kwargs) -> tuple[plt.figure, plt.axes]:
        """
        Returns a matplotlib figure and axes
        """
        fig_size = kwargs.get("figsize", (12, 6))
        dpi = kwargs.get("dpi", 300)
        fig, ax = plt.subplots(figsize=fig_size, dpi=dpi)
        ax.axis('equal')
        return fig, ax

    def add_beam_plot(self, fig, ax, **kwargs) -> tuple[plt.figure, plt.axes]:
        """
        Returns a fig, ax of a new subplot for a beam
        """
        beam_length = self.beam.length
        
        if not self.beam.depth:
            beam_x_ords = [0, beam_length]
            beam_y_ords = [0, 0]
        else:
            beam_x_ords = [0]*2 + [beam_length]*3 + [0]*2
            beam_y_ords = [0] + [self.beam.depth/2]*2 + [0] + [-self.beam.depth/2]*2 + [0]

        vertices = np.array(list(zip(beam_x_ords, beam_y_ords)))
        path = Path(vertices=vertices)
        path_patch = PathPatch(path, **kwargs)
         # Background beam plot to automatically set axes extents ## HACK
        ax.plot(beam_x_ords, beam_y_ords, alpha=0)
        ax.add_patch(path_patch)
        return fig, ax

    def add_beam_supports(self, fig, ax, **kwargs) -> tuple[plt.figure, plt.axes]:
        """
        Returns a fig, ax with supports added
        """
        lower_extent = 0
        for support in self.beam.supports:
            support_patch = svg_to_path.load_svg_file(self.support_svgs[int(support.fixity)])
            translation = graphics.get_svg_translation_transform(
                ax,
                support_patch,
                (support.location.x, -self.beam.depth/2),
                "top center",
                2
            )
            support_patch.set_transform(translation)
            support_patch.set(**kwargs)
            ax.add_patch(support_patch)

            ## Add node label
            if support.location.label.text is not None:
                ax.annotate(
                    f"{support.location.label.text}",
                    xy=(support.location.x, -self.beam.depth/2),
                    horizontalalignment='center',
                    size=14
                )
        return fig, ax


    def add_loads(self, fig, ax, **kwargs) -> tuple[plt.figure, plt.axes]:
        """
        Returns fig, ax with load graphics added
        """
        prop_cycle = mpl.rc_params()['axes.prop_cycle']
        colors = prop_cycle.by_key()['color']
        max_load_depth = self.strata['max_load_depth']
        scaling_loads = max_load_magnitudes(self.beam.loads)
        load_labels = list(sorted(set(load.label.text for load in self.beam.loads)))
        load_colors = {label_text: colors[idx] for idx, label_text in enumerate(load_labels)}
        y = self.strata['beam_top']
        for load in self.beam.loads:
            load_type = classify_load(load)
            display_magnitude = get_scaled_magnitude(load, scaling_loads, max_load_depth)
            if load_type == "POINT":
                x = load.start_location
                arrow_patch = graphics.arrow_at_coordinate(
                    point=(x, y), 
                    magnitude=display_magnitude, 
                    angle=load.alpha,
                    color=load_colors.get(load.label.text),
                    **kwargs
                )
                ax.add_patch(arrow_patch)
            elif load_type == "DISTRIBUTED":
                try:
                    start_magnitude, end_magnitude = display_magnitude
                except TypeError:
                    start_magnitude = end_magnitude = display_magnitude
                polygon_patch, arrows = graphics.distributed_load_region(
                    self.beam.length, 
                    start_magnitude,
                    load.start_location, 
                    end_magnitude,
                    load.end_location, 
                    y, 
                    load_colors.get(load.label.text), 
                    **kwargs,
                )
                ax.add_patch(polygon_patch)
                for arrow_patch in arrows:
                    ax.add_patch(arrow_patch)
            
        return fig, ax


    def add_dimensions(self, fig, ax, y_offset=0, **kwargs) -> tuple[plt.figure, plt.axes]:
        """
        Returns fig, ax with dimension graphics added
        """
        dim_tick_patch = svg_to_path.load_svg_file(self.misc_svgs["DIM_TICKS"])
        paths = []
        ticks = []
        for node in self.beam.dimensions:
            paths.append([node.x, y_offset])

            # Plot ticks
            dim_tick = copy.deepcopy(dim_tick_patch)
            transform = graphics.get_svg_translation_transform(
                ax,
                dim_tick_patch, 
                (node.x, y_offset), 
                "center center", 
                scale_factor=1, 
            )
            dim_tick.set_transform(transform)
            dim_tick.set(**kwargs)
            dim_tick.set_zorder(-3)
            ax.add_patch(dim_tick)

        # Plot dim labels
        prev_span = 0
        for span in self.beam.get_spans():
            ax.annotate(
                f"{span}",
                xy=(prev_span + span/2, y_offset-1),
                horizontalalignment='center',
                size=14
            )
            prev_span += span
        path = Path(np.array(paths))
        path_patch = PathPatch(path, **kwargs)
        ax.add_patch(path_patch)
        return fig, ax


    def add_node_labels(self, fig, ax, **kwargs) -> tuple[plt.figure, plt.axes]:
        """
        Returns fig, ax with node labels added
        """
        return fig, ax
                

    def get_label_text(label: Union[str, Label], **kwargs) -> str:
        """
        Returns the label text from the data in a label attribute on any object in the
        model module.
        """
        if isinstance(label, str): 
            return label
        elif isinstance(label, Label): 
            return label.text
        else: 
            return str(label)


def get_relative_load_depths(self, loads: list[Load]) -> dict[Optional[float]]:
    """
    Returns a list representing the relative maximum magnitudes of the loads
    in 'loads' on a scale of 0.0 to 1.0. If a returned value is None it represents
    that the relative magnitudes does not apply to this load type (e.g. moments).
    """
    max_magnitude_load = self.get_max_magnitude(loads)
    max_magnitude = max([max_magnitude_load.magnitude, max_magnitude_load.end_magnitude or 0])
    relative_depths = []
    for load in loads:
        if load.moment:
            relative_depths.append(None)
        else:
            current_max = max([load.magnitude, load.end_magnitude or 0])
            relative_depths.append(current_max / max_magnitude)
    return relative_depths


def get_max_magnitude(loads: list[Load]) -> Load:
    """
    Returns the Load with the absolute maximume load magnitude from all of the Load in 'loads'.
    """
    start_magnitude = max(loads, key=lambda x: abs(x.magnitude))
    end_magnitude = max(loads, key=lambda x: abs(x.end_magnitude) if x.end_magnitude else 0)
    max_magnitude = max([start_magnitude, end_magnitude or 0])
    return max_magnitude


def classify_load(load: Load) -> str:
    """
    Returns a str interpreting the type of load contained in load.
    Load categories:
    "POINT", "DISTRIBUTED", "POINT_MOMENT",
    """
    if load.moment:
        return "POINT_MOMENT"
    elif load.end_location is not None:
        return "DISTRIBUTED"
    else:
        return "POINT"


def max_load_magnitudes(loads: list[Load]) -> dict[str, float]:
    """
    Returns a dictionary representing the maximum magnitude for each 
    load category in 'loads'.
    The load categories are "POINT", "DISTRIBUTED", "POINT_MOMENT".
    """
    magnitudes = {"POINT": 0.0, "DISTRIBUTED": 0.0, "POINT_MOMENT": 0.0}
    for load in loads:
        load_type = classify_load(load)
        comparison_magnitude = magnitudes.get(load_type)
        scaling_magnitude = load.magnitude
        if load.end_magnitude is not None:
            if abs(load.end_magnitude) > abs(load.start_magnitude):
                scaling_magnitude = abs(load.end_magnitude)
        if comparison_magnitude < abs(scaling_magnitude):
            magnitudes[load_type] = abs(scaling_magnitude)
    return magnitudes


def get_scaled_magnitude(load: Load, max_magnitudes: dict, max_depth: float) -> Union[float, tuple[tuple]]:
    """
    Returns magnitude of 'load' scaled according to the maximum magnitude of its
    category in 'max_magnitudes' and according to 'max_depth' which is effectively
    the maximum magnitude the load can have in figure space.
    If 'load' is of category "DISTRIBUTED" then it will return a tuple of float
    representing the start and end magnitude.
    If 'load' is of category "POINT" or "POINT_MOMENT" then it will return a float
    representing the magnitude.
    """        
    load_type = classify_load(load)
    if load_type == "POINT":
        scaling_load = abs(load.magnitude)
        scaling_factor = abs(scaling_load / max_magnitudes[load_type])
        load_depth = scaling_factor * max_depth
        return load_depth
    elif load_type == "DISTRIBUTED":
        start_scaling_load = abs(load.magnitude)
        end_scaling_load = abs(load.end_magnitude) if load.end_magnitude is not None else None
        start_scaling_factor = abs(start_scaling_load / max_magnitudes[load_type])
        if end_scaling_load is not None:
            end_scaling_factor = abs(end_scaling_load / max_magnitudes[load_type])
        start_load_depth = start_scaling_factor * max_depth
        if end_scaling_load is not None:
            end_load_depth = end_scaling_factor * max_depth
        if end_scaling_load is not None:
            return (start_load_depth, end_load_depth)
        
        return start_load_depth
    elif load_type == "POINT_MOMENT":
        load_depth = scaling_factor * max_depth
        return load_depth
