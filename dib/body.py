"""A movable body in desktop pixel coordinates."""
from dataclasses import dataclass


@dataclass
class Body:
    """One ball: centre, radius, containing rectangle and motion state."""

    x: float
    y: float
    radius: float
    bounds: tuple
    vx: float = 0.0
    vy: float = 0.0
    angle: float = 0.0
    impact: float = 0.0
