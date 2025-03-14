SpaceMouse3Dconnexion QGIS Plugin
Overview
The SpaceMouse3Dconnexion QGIS Plugin enables professional-grade 3D navigation in QGIS using 3DConnexion SpaceMouse devices. It achieves this through direct HID communication, bypassing the need for additional drivers. This plugin is designed to provide seamless and intuitive 3D navigation for GIS professionals and enthusiasts.

Important Note
This plugin temporarily stops the 3DConnexion service while running to avoid conflicts with direct HID communication. The service is automatically restarted when:

The plugin is disabled

QGIS is closed

The plugin is unloaded

Features
Direct HID Device Communication: No additional drivers required.

6 Degrees of Freedom (6-DOF) Navigation: Full control over 3D movement and rotation.

Real-Time Response: Immediate feedback to device inputs.

Customizable Sensitivity Settings: Adjust translation and rotation sensitivity to suit your workflow.

Kalman Filtering: Ensures smooth and precise movement.

Multiple 3D View Support: Navigate multiple 3D views simultaneously.

Requirements
Hardware
3DConnexion SpaceMouse Device (Supported models):

SpaceMouse Enterprise

SpaceExplorer

SpaceNavigator

SpaceMouse USB

SpaceMouse Pro Wireless

SpaceMouse Pro

SpaceMouse Wireless

SpaceMouse Wireless [NEW]

SpacePilot

SpacePilot Pro

SpaceMouse Compact

SpaceNavigator for Notebooks (requires modification to pyspacemouse.py)

Other HID-compatible models

Software
QGIS 3.0 or later

Python Packages (automatically installed):

numpy >= 1.20.0

pyspacemouse >= 0.3.0

easyhid >= 0.0.9

Platform
Tested on Windows only

Installation
Method 1: QGIS Plugin Manager
Open QGIS.

Navigate to Plugins > Manage and Install Plugins.

Search for "SpaceMouse3Dconnexion".

Click Install.

Method 2: Manual Installation
Download the SpaceMouse3Dconnexion.zip file.

Extract the contents to your QGIS plugins directory:

Windows: %APPDATA%\QGIS\QGIS3\profiles\default\python\plugins

Restart QGIS.

Configuration
Initial Setup
Connect your SpaceMouse device to your computer.

Enable the plugin in QGIS.

Configure settings via the plugin dock.

Settings Guide
Movement Sensitivity: Adjusts translation response (range: 0.1-10.0).

Rotation Sensitivity: Adjusts rotation response (range: 0.1-10.0).

Update Interval: Controls input sampling rate (range: 1-100ms).

Threshold Values: Minimum input recognition (range: 0.001-0.1).

Adding Support for SpaceNavigator for Notebooks
To add support for the SpaceNavigator for Notebooks device, modify the pyspacemouse.py file as follows:

Locate the pyspacemouse.py file in your Python QGIS environment.

Open the file in a text editor.

Add the following code to the device_specs dictionary:

python
Copy
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
Save the file and restart QGIS.

Troubleshooting
Common Issues
Device Not Detected

Check the USB connection.

Restart QGIS.

Linux Permission Issues

bash
Copy
# Add udev rule for SpaceMouse devices
echo 'SUBSYSTEM=="hidraw", ATTRS{idVendor}=="256f", MODE="0666"' | sudo tee /etc/udev/rules.d/99-spacemouse.rules
sudo udevadm control --reload-rules
sudo udevadm trigger
Contact
For any issues or questions, please contact the author at denis.empisse@hotmail.com.

Additional Notes
Linux and macOS Support: The plugin is currently tested only on Windows. Support for Linux and macOS may be added in future updates.

Future Testing: If you plan to test and support other platforms, update the documentation accordingly.

Preparing for Submission
Include requirements.txt and dev-requirements.txt in your plugin package.

Verify plugin functionality on different operating systems and QGIS versions.

Zip your plugin directory, including all necessary files (__init__.py, SpaceMousePlugin.py, requirements.txt, dev-requirements.txt, icons, etc.).

Follow the QGIS plugin repository guidelines for submission.

Maintenance and Updates
Keep track of user feedback and issues.

Regularly update the plugin to fix bugs, add features, and ensure compatibility with new QGIS versions.
