# SpaceMouse3Dconnexion QGIS Plugin
## Overview
The SpaceMouse3Dconnexion QGIS Plugin enables professional-grade 3D navigation in QGIS using 3DConnexion SpaceMouse devices. It achieves this through direct HID communication, bypassing the need for additional drivers. This plugin is designed to provide seamless and intuitive 3D navigation for GIS professionals and enthusiasts.

## Important Note
This plugin temporarily stops the 3DConnexion service while running to avoid conflicts with direct HID communication. The service is automatically restarted when:

- The plugin is disabled
- QGIS is closed
- The plugin is unloaded

## Features
- Direct HID device communication (no drivers needed)
- 6 Degrees of Freedom (6-DOF) navigation
- Real-time response to device input
- Customizable sensitivity settings
- Kalman filtering for smooth movement
- Multiple 3D view support

## Requirements
### Hardware
- 3DConnexion SpaceMouse device (Supported models):
	- SpaceMouseEnterprise
	- SpaceExplorer
	- SpaceNavigator
	- SpaceMouseUSB
	- SpaceMouse Pro Wireless
	- SpaceMouse Pro
	- SpaceMouse Wireless
	- SpaceMouse Wireless [NEW]
	- SpacePilot
	- SpacePilot Pro
	- SpaceMouse Compact
	- SpaceNavigator for Notebooks
[Other HID-compatible models]

### Software
- QGIS 3.0 or later
- Python packages (automatically installed):
  * numpy >= 1.20.0
  * easyhid >= 0.0.9 (for device detection)
  * pywinusb (for HID communication on Windows)

 
### Platform
- Tested on Windows only
- Linux and macOS support is in development

### Installation
### Method 1: QGIS Plugin Manager
1. Open QGIS
2. Navigate to Plugins > Manage and Install Plugins
3. Search for "SpaceMouse3Dconnexion"
4. Click 'Install'

### Method 2: Manual Installation
1. Download SpaceMouse3Dconnexion.zip
2. Extract to your QGIS plugins directory:
	- Windows: %APPDATA%\QGIS\QGIS3\profiles\default\python\plugins
3. Restart QGIS

### Configuration
### Initial Setup
1. Connect SpaceMouse device
2. Enable plugin in QGIS
3. Configure settings via plugin dock

### Settings Guide
- Movement Sensitivity: Adjusts translation response (0.1-10.0)
- Rotation Sensitivity: Adjusts rotation response (0.1-10.0)
- Update Interval: Controls input sampling (1-100ms)
- Threshold Values: Minimum input recognition (0.001-0.1)

### Adding Support for New Devices
To add support for additional SpaceMouse devices, you can use the built-in device manager or manually modify the devices.json file:

## Using the Device Manager
1. In QGIS, go to the SpaceMouse3Dconnexion plugin menu
2. Select "Manage Devices"
3. Click "Add New Device" and follow the wizard

## Manual Configuration
1. Locate the devices.json file in the plugin directory
2. Add a new entry with the appropriate configuration:
ex : Devices.json
"Your Device Name": {
  "name": "Your Device Name",
  "hid_id": [vendor_id, product_id],
  "mappings": {
    "x": [1, 1, 2, 1],
    "y": [1, 3, 4, -1],
    "z": [1, 5, 6, -1],
    "roll": [2, 1, 2, -1],
    "pitch": [2, 3, 4, -1],
    "yaw": [2, 5, 6, 1]
  },
  "button_mapping": [
    [3, 1, 0],
    [3, 1, 1]
  ],
  "axis_scale": 327.0
}

3. Restart QGIS or reload the plugin

## Troubleshooting
### Common Issues
1. Device Not Detected

	- Check USB connection
	- Restart QGIS

	- Verify the device is listed in the device manager
	- Try using a different USB port
2. Plugin Not Working

	- Check if the 3DConnexion service is running (it should be stopped by the plugin)
	- Verify that the plugin is enabled in QGIS
	- Check the QGIS log for error messages

## Additional Notes
Linux and macOS Support: The plugin is currently tested primarily on Windows. 
Support for Linux and macOS is in development.
Future Testing: If you test the plugin on other platforms, please share your feedback to help improve cross-platform compatibility.