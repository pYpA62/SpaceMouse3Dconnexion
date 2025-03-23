# -*- coding: utf-8 -*-
"""
/***************************************************************************
 SpaceMouse3Dconnexion
                                 A QGIS plugin
 Control QGIS 3D view with 3Dconnexion SpaceMouse
                             -------------------
        begin                : 2023-01-01
        copyright            : (C) 2023 by Your Name
        email                : your.email@example.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = 'Denis Empisse'
__date__ = '2025-03-23'
__copyright__ = '(C) 2025 by Denis Empisse'

# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

# noinspection PyPep8Naming
def classFactory(iface):  # pylint: disable=invalid-name
    """Load SpaceMouse3Dconnexion class from file SpaceMouse3Dconnexion.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .SpaceMousePlugin import SpaceMousePlugin
    return SpaceMousePlugin(iface)

