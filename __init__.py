def classFactory(iface):
    from .neighbor_plugin import NeighborHighlightPlugin
    return NeighborHighlightPlugin(iface)