from __future__ import annotations
from typing import Union, Optional
from enum import IntEnum
from dataclasses import dataclass, fields
from matplotlib import pyplot
 

Number: Union[int, float]

@dataclass
class Label:
    """
    A generic class to define a label to be plotted.

    text: str - Label text
    x_offset: Optional, None - The x coordinate offset from the associated Node
    y_offset: Optional, None - The y coordinate offset from the associated Node
    text_properties: Optional, None - A dictionary of label display properties associated
        with the plotting backend. Passed on directly to the plotting backend.

    ## Examples
    LA00 = Label("")
    LA01 = Label("A", 0.5, 1.0)
    LA02 = Label("B", 1, 3, {"font_size": 1})
    """
    text: str
    x_offset: Optional[Number] = None
    y_offset: Optional[Number] = None
    text_properties: Optional[dict] = None

    def __str__(self):
        return _alternate_dataclass_repr(self)


@dataclass(order=True)
class Node:
    """
    A generic location on a beam's local axis. Nodes can be used to
    represent locations of supports, locations of loads, or locations of labels

    x: float or int - A value within the bounds of a beam's local axis. Must be a positive value.
    label: Optional[Union[str, Label]] = None. The label to associate with the node.

    ## Examples

    LA02 = Label("B", 1, 3, {"font_size": 1})

    N00 = Node(0, "A")
    N01 = Node(4.23, "B")
    N02 = Node(12, L02)
    """
    x: Number
    label: Optional[Union[Label, str]] = None

    def __str__(self):
        return _alternate_dataclass_repr(self)


class Fixity(IntEnum):
    """
    The Fixity quality that applies to a Support.
    FREE = 0
    H_ROLLER = 1
    V_ROLLER = -1
    PINNED = 2
    FIXED = 3

    # Examples:
    FREE = Fixity(0)
    H_ROLLER = Fixity(1)
    V_ROLLER = Fixity(-1)
    PINNED = Fixity(2)
    FIXED = Fixity(3)
    """
    H_ROLLER = 0
    V_ROLLER = 1
    PINNED = 2
    FIXED = 3
    H_SPRING = 4
    V_SPRING = 5
    M_SPRING = 6
    T_SPRING = 7



@dataclass
class Support:
    """
    A dataclass representing a support that may occur on a beam plot.
    location: Node - The location of the support
    fixity: fixity - The type of support to plot

    ## Examples
    N00 = Node(0, "A")
    N01 = Node(4.23, "B")
    N02 = Node(12, L02)

    S00 = Support(N00, 0)
    S01 = Support(N01, 1)
    S02 = Support(N02, 2)
    S03 = Support(N00, 3)
    """
    location: Union[Node, str, Number]
    fixity: Union[Fixity, int]
    label: Optional[Label] = None

    def __str__(self):
        return _alternate_dataclass_repr(self)


@dataclass
class Joint:
    """
    A dataclass representing a joint that may occur on a beam plot.
    location: Node - the location of the joint
    fixity: Fixity - the type of joint to plot
        Note: a fixity of 3 (fixed) at a joint will result in no
        joint being plotted (beam is assumed to be fixed).
    """
    location: Union[Node, str, Number]
    fixity: Union[Fixity, int]
    label: Optional[Label] = None

    def __str__(self):
        return _alternate_dataclass_repr(self)


@dataclass
class Load:
    """
    A generic dataclass representing any kind of load that may occur on a beam plot.

    type: str - May be one of "moment", "point", "linear" # Could also be an IntEnum
    magnitude: int or float - The magnitude of the load. If the load is of type "linear", then magnitude
        represents the starting magnitude of the linear load.
        +ve values: point in positive x,y-axis ("up", "right") and rotate anti-clock-wise.
        -ve values: point in negative x,y-axis ("down", "left") and rotate clock-wise.
    location: Node - The location on the beam of the load. If the load is of type "linear", then location
        represents the starting location of the linear load.
    end_magnitude: optional, None - If the load is of type "linear" then this represents the end magnitude
        of the linear load. If the type is "linear" and end_magnitude is None, then the linear load
        will be assumed to be a uniform load of the start magnitude.
        Ignored on types "moment" and "point".
        +ve values: point in positive x,y-axis ("up", "right") and rotate clock-wise.
        -ve values: point in negative x,y-axis ("down", "left") and rotate anti-clock-wise.
    end_location: optional, None - If the load is of type "linear" then this represents the end location
        of the linear load. If the type fo load is "linear" and end_location is None, then the linear load
        will be assumed to end at the end of the Beam object it is assigned to.
    alpha: float, 0.0 - describes the angle at which the load is to be applied. Measured in radians deviation 
        from vertical. Default value of 0.0 refers to a vertically applied load. Ignored if type is "moment".
        +ve values: rotates the "tail" of the load arrow(s) anti-clock-wise.
        -ve values: rotates the "tail" of the load arrow(s) clock-wise.

    ## Examples
    N00 = Node(0, "A")

    L00 = Load(45, N00) # Point load @ N00
    L01 = Load(45, N00, moment=True) # Point moment @ N00
    L02 = Load(45, N00, 5.2) # UDL from starting from N00 to ending at 5.2
    L03 = Load(45, N00, 5.2, 100) # Trapezoidal load: 45 @ N00 (start) -> 100 @ 5.2 (end)
    L04 = Load(45, N00, 5.2, moment=True) # Uniform distributed torsion load: 45 @ N00 (start) -> 5.2 (end)
    L05 = Load(45, N00, moment=True, alpha=90) # Point torsion @ N00
    L06 = Load(45, )
    """
    magnitude: Number
    start_location: Union[Node, str, Number]
    end_location: Optional[Union[Node, str, Number]] = None
    end_magnitude: Number = None
    moment: bool = False
    alpha: float = 0.0 # Angle in degrees
    label: Optional[Label] = None

    def __str__(self):
        return _alternate_dataclass_repr(self)


@dataclass
class Beam:
    """
    A dataclass representing a beam to plot.

    start_location: Node - The starting coordinate of the beam
    end_location: Node - The end coordinate of the beam
    supports: list[Support] - A list of supports along the beam to be plotted
    loads: list[Load] - Any list of loads along the beam to be plotted
    depth: Optional, None - The graphical depth of the beam to be plotted.
        If None, beam will be represented by a line with no thickness.
        The depth is in the same units as the start_location and end_location
        nodes.
    points_of_interest: Optional, None - A list of nodes that exist along the
        length of the beam that can be used for additional annotations.

    ## Examples
    LA00 = Label("A", 0.5, 1.0)
    LA01 = Label("B", 1, 3, {"font_size": 1})

    N00 = Node(0, L00)
    N01 = Node(4.23, L01)

    ROLLER = Fixity(0)
    PINNED = Fixity(2)

    S01 = Support(N01, PINNED)
    S02 = Support(N02, ROLLER)

    L00 = Load()
    L01 = Load()

    my_beam = Beam(
        start_location=N00, 
        end_location=N01, 
        supports=[S01, S02],
        loads=[L00, L01],
        depth=0.3,
    )
    """
    nodes: list[Union[Node, Number]]
    supports: Optional[list[Support]] = None
    loads: Optional[list[Load]] = None
    joints: Optional[list[Joint]] = None
    depth: Optional[Union[Number, list[Number]]] = None
    dimensions: Optional[list[Union[Node, str]]] = None
    fig = None

    def __post_init__(self):
        new_nodes = []
        for node in self.nodes:
            if isinstance(node, (float, int)):
                new_node = Node(node, label=Label(f"{node}"))
                new_nodes.append(new_node)
            elif hasattr(node, "label"):
                if isinstance(node.label, str):
                    node.label = Label(node.label)
                new_nodes.append(node)


        self.nodes = new_nodes

    def __str__(self):
        return _alternate_dataclass_repr(self)    

         

    def get_spans(self):
        """
        Returns the list of spans that exist on the beam as defined by
        the node locations.
        """
        spans = []
        prev_loc = 0
        for idx, node in enumerate(self.nodes):
            if idx == 0:
                prev_loc = node.x                
            else:
                current_span = abs(node.x - prev_loc)
                spans.append(current_span)
                prev_loc = node.x
        return spans



def nodes_from_spans(
    spans: list[Union[int, float]], 
    labels: Optional[list[Union[Label, str]]] = None
    ) -> list[Node]:
    """
    Returns a list of nodes based of the provided spans.
    Optionally, a list of labels can be supplied which will correspond to the new nodes.
    """
    if labels and len(labels) != len(spans) + 1:
        raise ValueError(
            "If labels is supplied, the number of labels should equal the number "
            f"of spans + 1. Span length: {len(spans)}, and, label length: {len(labels)} were passed."
            )

    nodes = []
    N00 = Node(0)
    N00.label = make_label(labels.pop(0)) if labels else None

    nodes.append(N00)
    prev_span = 0
    for idx, span in enumerate(spans):
        label = make_label(labels[idx]) if labels else None
        new_node = Node(span - prev_span, label)
        nodes.append(new_node)
    return nodes



def make_label(label: Union[str, Label]) -> Label:
    """
    Returns a new Label if a str is passed. 
    Returns the label if a Label is passed.
    Returns a new label if another object is passed using the result
    of str(label) as the label text.
    """
    if isinstance(label, str):
        return Label(text=label)
    elif isinstance(label, Label):
        return label
    else:
        return Label(text=str(label))


def _alternate_dataclass_repr(object) -> None:
    """
    Overrides the default dataclass repr by not printing fields that are
    set to None. i.e. Only prints fields which have values.
    This is for ease of reading.
    """
    populated_fields = {
        field.name: getattr(object, f"{field.name}")
        for field in fields(object)
        if getattr(object, f"{field.name}") is not None
    }
    class_name = object.__class__.__name__
    repr_string = f"{class_name}(" + ", ".join([f"{field}={value}" for field, value in populated_fields.items()]) + ")"
    return repr_string
