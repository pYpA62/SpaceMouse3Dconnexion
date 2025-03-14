from .SpaceMousePlugin import SpaceMousePlugin

# Required QGIS plugin factory function
def classFactory(iface):
    """
    Load SpaceMousePlugin class from file SpaceMousePlugin.
    
    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    return SpaceMousePlugin(iface)
