"""Chart layout for pyweft-ui's chart controls: data in, a scene out.

Everything here is plain Python with no page. It turns rows and settings
into a :class:`Scene` (shapes with pixel coordinates, a tooltip per
hoverable spot, a legend and a data table) that ``chart_view.weft`` draws
as SVG. So every chart shares one renderer, and layout is tested without a
browser.
"""

from .cartesian import cartesian
from .data import Series, Slice, cartesian_input, color_of, field, number, rows_of, slices_input
from .radial import pie, polar, radar
from .scales import LinearScale, fmt_tick, fmt_value, nice, ticks
from .scene import LegendItem, Mark, Scene, Tip

__all__ = [
    "cartesian", "pie", "polar", "radar",
    "Series", "Slice", "cartesian_input", "slices_input", "rows_of", "field", "number", "color_of",
    "LinearScale", "ticks", "nice", "fmt_value", "fmt_tick",
    "Scene", "Mark", "Tip", "LegendItem",
]
