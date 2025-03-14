# SpaceMouse3Dconnexion QGIS Plugin

## Overview
The SpaceMouse3Dconnexion QGIS Plugin enables professional-grade 3D navigation in QGIS using 3DConnexion SpaceMouse devices.
It achieves this through direct HID communication, bypassing the need for additional drivers.
This plugin is designed to provide seamless and intuitive 3D navigation for GIS professionals and enthusiasts.

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
  * SpaceMouseEnterprise
  * SpaceExplorer
  * SpaceNavigator
  * SpaceMouseUSB
  * SpaceMouse Pro Wireless
  * SpaceMouse Pro
  * SpaceMouse Wireless
  * SpaceMouse Wireless [NEW]
  * SpacePilot
  * SpacePilot Pro
  * SpaceMouse Compact
  * SpaceNavigator for Notebooks (requires modification to `pyspacemouse.py`)
  * [Other HID-compatible models]

### Software
- QGIS 3.0 or later
- Python packages (automatically installed):
  * numpy >= 1.20.0
  * pyspacemouse >= 0.3.0
  * easyhid >= 0.0.9

### Platform
- **Tested on Windows only**

## Installation
### Method 1: QGIS Plugin Manager
1. Open QGIS
2. Navigate to `Plugins` > `Manage and Install Plugins`
3. Search for "SpaceMouse3Dconnexion"
4. Click `Install`

### Method 2: Manual Installation
1. Download `SpaceMouse3Dconnexion.zip`
2. Extract to your QGIS plugins directory:
   - Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins`
3. Restart QGIS

## Configuration
### Initial Setup
1. Connect SpaceMouse device
2. Enable plugin in QGIS
3. Configure settings via plugin dock

### Settings Guide
- **Movement Sensitivity**: Adjusts translation response (0.1-10.0)
- **Rotation Sensitivity**: Adjusts rotation response (0.1-10.0)
- **Update Interval**: Controls input sampling (1-100ms)
- **Threshold Values**: Minimum input recognition (0.001-0.1)

## Adding Support for SpaceNavigator for Notebooks
To add support for the "SpaceNavigator for Notebooks" device, you need to modify the `pyspacemouse.py` file. Follow these steps:

1. Locate the `pyspacemouse.py` file in your Python QGIS environment.
2. Open the file in a text editor.
3. Add the following code to the `device_specs` dictionary:

    ```python
    # the IDs for the supported devices
    # Each ID maps a device name to a DeviceSpec object
    device_specs = {
        # other devices …

        "SpaceNavigator_Notebook": DeviceSpec(
            name="SpaceNavigator for Notebooks",
            # Vendor ID and Product ID
            hid_id=[0x46D, 0xC628],
            # LED HID usage code pair
            led_id=[0x8, 0x4B],
            mappings={
                "x": AxisSpec(channel=1, byte1=1, byte2=2, scale=1),
                "y": AxisSpec(channel=1, byte1=3, byte2=4, scale=-1),
                "z": AxisSpec(channel=1, byte1=5, byte2=6, scale=-1),
                "pitch": AxisSpec(channel=2, byte1=1, byte2=2, scale=-1),
                "roll": AxisSpec(channel=2, byte1=3, byte2=4, scale=-1),
                "yaw": AxisSpec(channel=2, byte1=5, byte2=6, scale=1),
            },
            button_mapping=[
                ButtonSpec(channel=3, byte=1, bit=0),  # LEFT BUTTON
                ButtonSpec(channel=3, byte=1, bit=1),  # RIGHT BUTTON
            ],
            axis_scale=350.0,  # Adjust this value if necessary
        ),
        # Add other devices here if needed
    }
    ```

4. Save the file and restart QGIS.

## Troubleshooting
### Common Issues
1. **Device Not Detected**
   - Check USB connection
   - Restart QGIS



## Contact
For any issues or questions, please contact the author at denis.empisse@hotmail.com.

## Additional Notes
Linux and macOS Support: The plugin is currently tested only on Windows. Support for Linux and macOS may be added in future updates.

Future Testing: If you plan to test and support other platforms, update the documentation accordingly.

## Keywords
QGIS, SpaceMouse, 3Dconnexion, QGIS Plugin, HID Input, 3D Navigation, Python, 3DMouse, QGIS 3D
