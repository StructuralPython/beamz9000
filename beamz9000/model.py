from __future__ import annotations
from typing import Union, Optional
from enum import IntEnum
from dataclasses import dataclass, fields
from matplotlib import pyplot
 

Number: Union[int, float]
NUMBER = (float, int)

@dataclass
class Label:
    """
    A generic class to define a label to be plotted.

    text: str - Label text
    x_offset: Optional, None - The x coordinate offset from the associated Node
    y_offset: Optional, None - The y coordinate offset from the associated Node
    text_properties: Optional, None - A dictionary of label display properties associated
        with the plotting backend. Passed on directly to the plotting backend.
        Currently only matplotlib is supported as a plotting backend.

    ## Examples
    LA00 = Label("")
    LA01 = Label("A", 0.5, 1.0)
    LA02 = Label("B", 1, 3, {"font_size": 1})
    """
    text: Optional[str] = None
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

    def __post_init__(self):
        if isinstance(self.label, str):
            self.label = Label(self.label)
        elif self.label is None:
            self.label = Label()

    def __str__(self):
        return _alternate_dataclass_repr(self)


class Fixity(IntEnum):
    """
    The Fixity quality that applies to a Support.
    H_ROLLER = 0
    V_ROLLER = 1 # Applies only at beam ends
    PINNED = 2 
    FIXED = 3 # Applies only at beam ends
    V_SPRING = 4
    M_SPRING = 5

    # Examples:
    H_ROLLER = Fixity(0)
    V_ROLLER = Fixity(1)
    PINNED = Fixity(2)
    FIXED = Fixity(3)
    V_SPRING = Fixity(4)
    M_SPRING = Fixity(5)
    """
    H_ROLLER = 0
    V_ROLLER = 1
    PINNED = 2
    FIXED = 3
    V_SPRING = 4
    M_SPRING = 5


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

    def __post_init__(self):
        if isinstance(self.location, NUMBER):
            node = Node(self.location, label=Label(self.label))
            self.location = node
        if self.label is None or isinstance(self.label, str):
            self.label = Label(self.label)

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

    def __post_init__(self):
        if isinstance(self.label, str):
            self.label = Label(self.label)

    def __str__(self):
        return _alternate_dataclass_repr(self)


@dataclass
class Load:
    """
    A generic dataclass representing any kind of load that may occur on a beam plot.

    magnitude: int or float - The magnitude of the load. If the load is of type "linear", then magnitude
        represents the starting magnitude of the linear load.
        +ve values: point in positive x,y-axis ("up", "right") and rotate anti-clock-wise.
        -ve values: point in negative x,y-axis ("down", "left") and rotate clock-wise.
    location: Node - The location on the beam of the load. If the load is of type "linear", then location
        represents the starting location of the linear load.
    end_location: optional, None - If provided, the load will be interpreted as a trapezoidal
        load starting from 'location' and ending at the end of the beam with a magnitude of 'end_magnitude'.
        If moment=True, then end_magnitude is ignored.
        If torque=True, then the load will be a "trapezoidal" distributed torque load ending at the
        end of the beam.
        +ve values: point in positive x,y-axis ("up", "right") and rotate clock-wise.
        -ve values: point in negative x,y-axis ("down", "left") and rotate anti-clock-wise.
    end_magnitude: optional, None - For a distributed load or a distributed torque, represents the location
        where the load ends. If end_location is provided, then end_magnitude must also be supplied.
    alpha: float, 0.0 - Applies only to point loads. Describes the angle at which the load is to be applied. 
        Measured in degrees deviation from vertical. Default value of 0.0 refers to a vertically applied load
        Ignored if either moment=True or torque=True.
        +ve values: rotates the "tail" of the load arrow(s) anti-clock-wise.
        -ve values: rotates the "tail" of the load arrow(s) clock-wise.
    moment: bool - If True, the load will be interpreted as a point moment with 'magnitude' at 'location'

    ## Examples
    N00 = Node(0, "A")

    L00 = Load(45, N00) # Point load @ N00
    L01 = Load(45, N00, moment=True) # Point moment @ N00
    L02 = Load(45, N00, 5.2) # UDL from starting from N00 and ending at 5.2
    L03 = Load(45, N00, 5.2, 100) # Trapezoidal load: 45 @ N00 (start) -> 100 @ 5.2 (end)
    L04 = Load(45, N00, 6) # UDL with magnitude of 45 over the beam length (of 6)
    """
    magnitude: Number
    start_location: Union[Node, str, Number]
    end_location: Optional[Union[Node, str, Number]] = None
    end_magnitude: Number = None
    moment: bool = False
    alpha: float = 0.0 # Angle in degrees deviation from vertical
    label: Optional[Label] = None

    def __post_init__(self):
        if isinstance(self.label, str):
            self.label = Label(self.label)
        elif self.label is None:
            self.label = Label()

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
    nodes: list[Union[Node, Number, str]]
    supports: Optional[list[Support]] = None
    loads: Optional[list[Load]] = None
    joints: Optional[list[Joint]] = None
    depth: Optional[Union[Number, list[Number]]] = None
    dimensions: Optional[list[Union[Node, Number, str]]] = None

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

        for support in self.supports:
            if isinstance(support.location, str):
                node = _lookup_node(support, self.nodes)
                if node is None:
                    raise ValueError(f"Support is at node with label: {support} but no node with this label exists.")
                else:
                    support.location = node

        processed_dimensions = []
        for loc in self.dimensions:
            if isinstance(loc, Node):
                processed_dimensions.append(loc)
            elif isinstance(loc, NUMBER):
                node = Node(loc)
                processed_dimensions.append(node)
            elif isinstance(loc, str):
                node = _lookup_node(loc, self.nodes)
                if node is None:
                    raise ValueError(f"A dimension is given for a node with label: {loc} but no node with this label exists.")
                else:
                    processed_dimensions.append(node)
        self.dimensions = processed_dimensions
        if self.depth is None:
            self.depth = 0

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

    @property
    def length(self):
        beam_spans = self.get_spans()
        beam_length = sum(beam_spans)
        return beam_length



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


def _lookup_node(node_label: str, nodes: list[Node]) -> Optional[Node]:
    """
    Returns a Node object if 'node_label' is a match for node.label in 'nodes'.
    Returns None, otherwise.
    """
    node = next((node for node in nodes if node.label == node_label)) or None
    return node
