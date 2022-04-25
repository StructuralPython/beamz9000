from typing import Optional
from beamz9000.model import Node, Label

def node_offset(x: float, node: Node, label: Optional[Label] = None) -> Node:
    """
    Returns a Node offset 'x' away from 'node'. If given, 'label' is added to
    the returned Node.
    """
    pass