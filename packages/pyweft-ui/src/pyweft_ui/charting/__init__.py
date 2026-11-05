"""Chart layout for pyweft-ui's chart controls: data in, a scene out.

Everything here is plain Python with no page. It turns rows and settings
into a :class:`Scene` (shapes with pixel coordinates, a tooltip per
hoverable spot, a legend and a data table) that ``chart_view.weft`` draws
as SVG. So every chart shares one renderer, and layout is tested without a
browser.
"""

from .business import funnel, gauge, waterfall
from .cartesian import cartesian
from .distribution import Group, boxplot, groups_input, histogram
from .finance import Candle, candles_input, candlestick
from .flow import links_input, sankey
from .hierarchy import Node, squarify, tree_input, treemap
from .matrix import calendar, correlation, days_input, heat_input, heatmap
from .data import Series, Slice, cartesian_input, color_of, field, number, rows_of, slices_input
from .radial import pie, polar, radar
from .scales import LinearScale, fmt_tick, fmt_value, nice, ticks
from .scene import LegendItem, Mark, Scene, Tip
from .stats import Fit, kde, linear_fit, moving_average, pearson, quantile, spearman, summary
from .xy import Point, XYSeries, scatter, sparkline, xy_input

__all__ = [
    "cartesian", "pie", "polar", "radar", "scatter", "sparkline", "gauge", "funnel", "waterfall",
    "histogram", "boxplot", "heatmap", "calendar", "candlestick", "treemap", "sankey",
    "xy_input", "groups_input", "heat_input", "correlation", "days_input", "candles_input", "tree_input",
    "links_input", "squarify", "Point", "XYSeries", "Group", "Candle", "Node",
    "linear_fit", "Fit", "kde", "moving_average", "pearson", "spearman", "quantile", "summary",
    "Series", "Slice", "cartesian_input", "slices_input", "rows_of", "field", "number", "color_of",
    "LinearScale", "ticks", "nice", "fmt_value", "fmt_tick",
    "Scene", "Mark", "Tip", "LegendItem",
]
