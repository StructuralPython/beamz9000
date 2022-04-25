from typing import Union, Optional
import matplotlib.pyplot as plt
import pathlib
from beamz9000.model import Label, Node, Support, Fixity, Joint, Beam
import beamz9000.graphics as graphics
import beamz9000.svg_to_path as svg_to_path

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
            0: pathlib.Path(__file__).parent / "svg_supports" / self.style / "H_ROLLER.svg",
            1: pathlib.Path(__file__).parent / "svg_supports" / self.style / "V_ROLLER.svg",
            2: pathlib.Path(__file__).parent / "svg_supports" / self.style / "PINNED.svg",
            3: pathlib.Path(__file__).parent / "svg_supports" / self.style / "FIXED.svg",
            4: pathlib.Path(__file__).parent / "svg_supports" / self.style / "H_SPRING.svg",
            5: pathlib.Path(__file__).parent / "svg_supports" / self.style / "V_SPRING.svg",
            6: pathlib.Path(__file__).parent / "svg_supports" / self.style / "M_SPRING.svg",
            7: pathlib.Path(__file__).parent / "svg_supports" / self.style / "T_SPRING.svg",
        }
        

    def plot(self, style='default', **kwargs):
        fig, ax = self.init_plot()
        fig, ax = self.add_beam_plot(fig, ax, **kwargs)
        fig, ax = self.add_loads(fig, ax, **kwargs)
        fig, ax = self.add_beam_supports(fig, ax, **kwargs)
        fig, ax = self.add_node_labels(fig, ax, **kwargs)
        fig, ax = self.add_dimensions(fig, ax, **kwargs)

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
        beam_spans = self.beam.get_spans()
        beam_length = sum(beam_spans)
        if not self.beam.depth:
            beam_x_ords = [0, beam_length]
            beam_y_ords = [0, 0]
        else:
            beam_x_ords = [0]*2 + [beam_length]*3 + [0]*2
            beam_y_ords = [0] + [self.beam.depth/2]*2 + [0] + [-self.beam.depth/2]*2 + [0]
        ax.plot(beam_x_ords, beam_y_ords)
        return fig, ax

    def add_beam_supports(self, fig, ax, **kwargs) -> tuple[plt.figure, plt.axes]:
        """
        Returns a fig, ax with supports added
        """
        for support in self.beam.supports:
            support_patch = svg_to_path.load_svg_file(self.support_svgs[int(support.fixity)])
            translation = graphics.get_svg_translation_transform(ax, support_patch, (support.location.x, -self.beam.depth/2), "top center", 2)
            support_patch.set_transform(translation)
            support_patch.set(**kwargs)
            # print((support_patch.get_verts()))
            ax.add_patch(support_patch)
        return fig, ax


    def add_loads(self, fig, ax, **kwargs) -> tuple[plt.figure, plt.axes]:
        """
        Returns fig, ax with load graphics added
        """
        return fig, ax


    def add_dimensions(self, fig, ax, **kwargs) -> tuple[plt.figure, plt.axes]:
        """
        Returns fig, ax with dimension graphics added
        """
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