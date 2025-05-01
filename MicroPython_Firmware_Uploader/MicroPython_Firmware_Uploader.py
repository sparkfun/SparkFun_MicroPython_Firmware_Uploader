"""
This is a Python3 PyQt5 firmware upload GUI for SparkFun MicroPython devices.

MIT license

Please see the LICENSE.md for more details

"""

# import action things - the .syntax is used since these are part of the package
from .au_worker import AUxWorker
from .au_action import AxJob
from .au_act_esptool import AUxEsptoolDetectFlash, AUxEsptoolUploadFirmware, AUxEsptoolResetESP32, \
    AUxEsptoolEraseFlash
from .mpremote_utils import MPRemoteSession
from .au_act_rp2 import AUxRp2UploadRp2
from .au_act_teensy import AUxTeensyUploadTeensy

import darkdetect
import sys
import os
import os.path
import platform

import serial

from time import sleep

from typing import Iterator, Tuple

# Includes for interacting with GitHub API
import requests
from datetime import datetime

# Includes for interacting directly with firmware files
import zipfile
import shutil
import psutil

from re import sub

from PyQt5.QtCore import QSettings, QProcess, QTimer, Qt, QIODevice, pyqtSignal, pyqtSlot, QObject, QSize
from PyQt5.QtWidgets import QWidget, QLabel, QComboBox, QGridLayout, \
    QPushButton, QApplication, QLineEdit, QFileDialog, QPlainTextEdit, \
    QAction, QActionGroup, QMenu, QMenuBar, QMainWindow, QMessageBox, \
    QDialog, QVBoxLayout, QProgressBar, QHBoxLayout, QFrame, QListWidget, \
    QSpacerItem, QLayout, QSizePolicy, QListWidgetItem
from PyQt5.QtGui import QCloseEvent, QTextCursor, QIcon, QFont
from PyQt5.QtSerialPort import QSerialPort, QSerialPortInfo
from json import load

_APP_NAME = "SparkFun MicroPython Firmware Uploader"

# sub folder for our resource files
_RESOURCE_DIRECTORY = "resource"

# Repository to check for releases
_RELEASE_REPO = "sparkfun/micropython"

# This is the string that will be appended to the latest release
_LATEST_DECORATOR = " (latest)"

# This is the string for selections of a local firmware file
_LOCAL_DECORATOR = "Local"

# This is the string that will be used to represent board auto detection
_AUTO_DETECT_DECORATOR = "Auto Detect"

# The messages to be displayed in the GUI for the buttons
_DEVICE_CHOICE_DECORATOR = "CHOOSE DEVICE"
_FIRMWARE_CHOICE_DECORATOR = "CHOOSE FIRMWARE"
_PORT_CHOICE_DECORATOR = "CHOOSE PORT"

# This is the string prior to the board name in firmware file names
_BOARD_NAME_PREFIX = "MICROPYTHON_"

# These are other prefixes for other versions of the firmware builds
_ALT_NAME_PREFIXES = ["MINIMAL_MICROPYTHON_"]

# Temporary directory for storing the firmware files
_TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")

# Maximum amount of time to wait for a new drive to be mounted after user says they have pressed the boot button
_MAX_DRIVE_WAIT_SEC = 2.0


#https://stackoverflow.com/a/50914550
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, _RESOURCE_DIRECTORY, relative_path)

def get_version(rel_path: str) -> str:
    try: 
        with open(resource_path(rel_path), encoding='utf-8') as fp:
            for line in fp.read().splitlines():
                if line.startswith("__version__"):
                    delim = '"' if '"' in line else "'"
                    return line.split(delim)[1]
            raise RuntimeError("Unable to find version string.")
    except:
        raise RuntimeError("Unable to find _version.py.")

_APP_VERSION = get_version("_version.py")

_BOARD_MANIFEST = None
try: 
    with open(resource_path("board_manifest.json"), 'r') as f:
        _BOARD_MANIFEST = load(f)
except Exception as e:
    # print("Error loading board manifest: ", e)
    print("No board manifest found, some features disabled.")
    print("Tried to find the manifest in: ", resource_path("board_manifest.json"))
    print("Check your installation to make sure that the resource files are included.")
    pass 

def strip_alt_prefixes(name: str) -> str:
    """Strip the prefixes from the name."""
    for prefix in _ALT_NAME_PREFIXES:
        name = name.replace(prefix, "")
    
    # Add back in the BOARD_NAME_PREFIX if it is not there
    if not name.startswith(_BOARD_NAME_PREFIX):
        name = _BOARD_NAME_PREFIX + name

    return name

def gen_serial_ports() -> Iterator[Tuple[str, str, str]]:
    """Return all available serial ports."""
    ports = QSerialPortInfo.availablePorts()
    return ((p.description(), p.portName(), p.systemLocation()) for p in ports)

# noinspection PyArgumentList
class PopupWindow(QDialog):
    def __init__(self, items=None, title="Pop-up Window", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # Remove the "help" button
        self.list_widget = QListWidget(self)
        self.list_widget.setFocusPolicy(Qt.NoFocus)  # Disable focus on the list widget
        self.list_widget.setIconSize(QSize(64, 64))  # Set icon size for the list items

        if items:
            for item in items:
                self.list_widget.addItem(item)  # Add each item to the list widget

        self.list_widget.itemClicked.connect(self.item_selected)  # Connect item click signal to handler
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)  # Remove margins
        layout.addWidget(self.list_widget)
        self.setLayout(layout)
        self.parent = parent

    def item_selected(self, item):
        if self.parent:  # Check if parent exists
            self.parent.setText(item.text())  # Change button text to selected item's text
            self.accept()  # Close the popup window properly

class PopupListButton(QPushButton):
    textChanged = pyqtSignal(str)

    def __init__(self, text, items=None, title="Pop-up Window", parent=None, popUpCallbacks=None, addTooltip=False):
        super().__init__(text, parent)
        self.items = items or []  # Default to an empty list if no items are provided
        self.popUpTitle = title
        self.clicked.connect(self.open_popup)
        self.popup = None
        self.popUpCallbacks = popUpCallbacks  # Callbacks to run before opening the popup
        self.addTooltip = addTooltip  # Flag to determine if we should add a tooltip
        self.storedDataDict = {}  # Dictionary to store data for each item. Maps item text to stored data of any type

    def open_popup(self):
        for callback in self.popUpCallbacks or []:
            callback()

        # Recreate the popup window with the current items to ensure they are visible
        if self.items is not None:
            try:
                items_to_show = [item.clone() for item in self.items]  # Clone items to avoid modifying the original list (was necessary)
            except AttributeError: # For when strings are passed in instead of QListWidgetItems
                items_to_show = self.items
        
        self.popup = PopupWindow(items_to_show, self.popUpTitle, self)
        self.popup.resize(600, 400)  # Set a larger size for the popup window
        self.popup.show()

    def addIconItem(self, text: str, description: str, iconPath: str, storedData=None) -> None:
        """Add an item with a description and an icon to the popup items."""
        icon = QIcon(iconPath)
        item = QListWidgetItem(icon, text)
        # item.setToolTip(description)  # Set the tooltip to show the description
        item.setSizeHint(QSize(400, 100))
        self.items.append(item)  # Add the item to the list of items
        if storedData is not None:
            self.storedDataDict[text] = storedData
    
    def setText(self, text: str) -> None:
        """Set the text of the button."""
        super().setText(text)  # Call the parent class's setText method
        if self.addTooltip:
            self.setToolTip(text) # Set the tooltip to mirror the text (helps for long text)
        self.textChanged.emit(text)  # Emit the textChanged signal

    def getStoredData(self, text: str) -> str:
        """Get the stored data for the item with the given text."""
        return self.storedDataDict.get(text, None)

# This is extensible such that if we release other firmware versions per-board we can update this class
# This class contains the name of the file, the name to display in the GUI, whether the file has qwiic drivers,
# and the processor that we assume it is for
class FirmwareFile(): 
    def __init__(self, name: str, displayName: str, hasQwiic: bool, processor: str, device: str, mpHwName) -> None:
        self.name = name
        self.displayName = displayName
        self.hasQwiic = hasQwiic
        self.processor = processor
        self.device = device
        self.mpHwName = mpHwName
    
    # Alternate constructor that takes the firmware file name and parses it to get the other features
    @classmethod
    def from_file(cls, firmwareFile: str) -> 'FirmwareFile':
        name = firmwareFile
        device = processor = mpHwName = None
        
        # Try to determine our values from the board manifest
        no_prefix_name = strip_alt_prefixes(name)

        # Find the device in the manifest based on the firmware file name
        for board in _BOARD_MANIFEST.keys():
            if _BOARD_MANIFEST[board]["default_fw_name"] == no_prefix_name:
                device = board
                processor = _BOARD_MANIFEST[board]["processor_type"]
                mpHwName = _BOARD_MANIFEST[board]["micropy_hw_board_name"]

        # If we didn't find the device in the manifest, we'll try to parse it from the name
        # Devine the device name from the firmware file name without the manifest
        if device is None:
            device = strip_alt_prefixes(name).split('.')[0]
            
            device = device.replace(_BOARD_NAME_PREFIX, "").replace("_", " ").title()

        displayName = device + " Firmware"
        
        # Devine the MicroPython device name from the firmware file name
        if mpHwName is None:
            mpHwName = "SparkFun " + device

        # Devine the processor type from the firmware file name
        if processor is None:
            if firmwareFile.endswith(".zip"):
                processor = "ESP32"
            elif firmwareFile.endswith(".uf2"):
                processor = "RP2"
            elif firmwareFile.endswith(".hex"):
                processor = "Teensy"

        # Check if the file has qwiic drivers (if it is a minimal file)
        hasQwiic = not firmwareFile.startswith("MINIMAL")

        if hasQwiic:
            displayName = displayName + " (With Qwiic Drivers)"
        else:
            displayName = displayName + " (Minimal Build)"

        return cls(name, displayName, hasQwiic, processor, device, mpHwName)

    def board_image_path(self) -> str:
        """Return the path to the image for the firmware file."""
        # we can use the name of this fw file object to find the image name in the manifest
        try:
            image_name = _BOARD_MANIFEST[self.device]["image_name"]
            if os.path.exists(resource_path(image_name)):
                # print("Found image for: ", self.name)
                return resource_path(image_name)
        except:
            #print("Error getting image path for firmware file: ", self.name)
            pass
        
        return resource_path("default_board_img.png")

    def fw_image_path(self) -> str:
        """
        Firmware images should be in resource directory with the name fw_<prefix_lower_case>.jpg.
        
        For now we only have two images, but using the same naming convention we can easily add more images.
        """
        for _prefix in _ALT_NAME_PREFIXES:
            if self.name.startswith(_prefix):
                return resource_path("fw_" + _prefix.lower() + ".jpg")
        
        return resource_path("fw_" + _BOARD_NAME_PREFIX.lower() + ".jpg")

    def __str__(self) -> str:
        return self.displayName

    def description(self) -> str:
        # We'll build up a brief description of the file based on it's features
        # We can add more features later if we want to
        descripiton = "SparkFun MicroPython firmware for the " + self.displayName + " board.\n"

        if self.hasQwiic:
            descripiton += "It has Qwiic drivers installed.\n"
        else:
            descripiton += "It is a minimal build.\n"


class MainWidget(QWidget):
    """Main Widget."""

    sig_message = pyqtSignal(str)
    sig_finished = pyqtSignal(int, str, int)
    sig_progress = pyqtSignal(int)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)

        # ---------------------------- Variables ----------------------------
        self.flashSize = 0
        self.latestRelease = ""
        self.firmwareDict = {} # Dictionary mapping release names to list of firmware file objects (release -> all firmware for all boards)
        self.deviceDict = {} # Dictionary mapping device names to list of firmware file objects (device -> all firmware for that device from latest release)
        self.offline = False

        # ---------------------------- Widgets ----------------------------
        # Page 1 Widgets:
        # Create a popup button with a list of devices from the latest release
        self.device_button = PopupListButton(
            text = _DEVICE_CHOICE_DECORATOR,
            items = None,
            title = "SparkFun Device",
            parent = self
        )
        
        # Make the device label centered over the button it is associated with
        self.device_label = QLabel(self.tr('SparkFun Device'))
        boldFont = self.device_label.font()
        boldFont.setBold(True)
        self.device_label.setFont(boldFont)
        self.device_label.setAlignment(Qt.AlignCenter)
        self.device_label.setBuddy(self.device_button)

        self.firmware_button = PopupListButton(
            text = _FIRMWARE_CHOICE_DECORATOR,
            items = None,
            title = "Firmware",
            parent = self,
            addTooltip=True,
        )

        # Make the firmware label centered over the button it is associated with
        self.firmware_label = QLabel(self.tr('Firmware'))
        self.firmware_label.setFont(boldFont)
        self.firmware_label.setAlignment(Qt.AlignCenter)
        self.firmware_label.setBuddy(self.firmware_button)

        # Attach the update_firmware_list method to the device button's textChanged signal
        self.device_button.textChanged.connect(self.update_firmware_list)

        # Populate the device button with the list of devices from the latest release
        # Add an automatic device detection option to the list of devices
        self.device_button.addIconItem(_AUTO_DETECT_DECORATOR, "Automatically detect the device", resource_path("auto_detect.png"))
        
        for device in self.get_device_list():
            self.device_button.addIconItem(device, "", resource_path(_BOARD_MANIFEST[device]["image_name"]))

        # Add the local firmware option to the list of firmware files
        self.firmware_button.addIconItem(_LOCAL_DECORATOR, "Local firmware file", resource_path("fw_local.png"))

        # Attach the browse callback to the firmware button's textChanged signal
        self.firmware_button.textChanged.connect(self.on_fw_button_pressed)

        # Port Popup Button
        self.port_button = PopupListButton(
            text = _PORT_CHOICE_DECORATOR,
            items = None,
            title = "Serial Port",
            parent = self,
            popUpCallbacks = [self.update_com_ports]
        )
        
        # Make the port label centered over the button it is associated with
        self.port_label = QLabel(self.tr('Serial Port'))
        self.port_label.setFont(boldFont)
        self.port_label.setAlignment(Qt.AlignCenter)
        self.port_label.setBuddy(self.port_button)

        # Upload Button
        myFont=QFont()
        myFont.setBold(True)
        self.upload_btn = QPushButton(self.tr('Upload'))
        self.upload_btn.setFont(myFont)
        self.upload_btn.clicked.connect(self.on_upload_btn_pressed)

        # Page 2 Widgets:
        # Messages Bar
        self.messages_label = QLabel(self.tr('UPLOAD STATUS:'))
        self.messages_label.setFont(boldFont)

        # Messages Window
        self.messageBox = QPlainTextEdit()
        color =  "424242"
        self.messageBox.setStyleSheet("QPlainTextEdit { color: #" + color + ";}")
        self.messageBox.setReadOnly(True)
        self.messageBox.clear()

        # Back Button to go back to page 1
        self.back_btn = QPushButton(self.tr('Back'))
        self.back_btn.setFont(myFont)
        self.back_btn.clicked.connect(self.switch_to_page_one)

        # Progress Bar
        self.progress_label = QLabel(self.tr('RP2 Upload Progress:'))
        self.progress_bar = QProgressBar()
        self.progress_label.setBuddy(self.progress_bar)
        self.progress_bar.setValue(0)
        self.progress_bar.hide()
        self.progress_label.hide()

        self.switch_to_page_one()

        # ---------------------------- Layout ----------------------------
        # Arrange Layout
        layout = QGridLayout()
        layout.setSpacing(5)  # Remove spacing between widgets

        # Set up the layout for the widgets
        # Add spacer items such that our device button and label are actually in their desired row and column
        layout.addItem(QSpacerItem(40, 20), 0, 0)
        layout.addItem(QSpacerItem(20, 40), 1, 0)

        # add the device label
        layout.addWidget(self.device_label, 3, 3, 1, 1)  # Device label

        self.device_button.setMinimumWidth(250)  # Set a minimum width for the button
        self.device_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # Allow the button to expand horizontally
        layout.addWidget(self.device_button, 4, 3)

        # Add a spacer between the device elements and the firmware elements
        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding), 3, 4, 2, 1)

        # Add the firmware label and button
        layout.addWidget(self.firmware_label, 3, 5, 1, 1)  # Firmware label

        self.firmware_button.setMinimumWidth(250)  # Set a minimum width for the button
        self.firmware_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # Allow the button to expand horizontally
        layout.addWidget(self.firmware_button, 4, 5)

        # Add a spacer between the firmware elements and the port elements
        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding), 3, 6, 2, 1)

        # Add the port label and button
        layout.addWidget(self.port_label, 3, 7, 1, 1)  # Port label

        self.port_button.setMinimumWidth(250)  # Set a minimum width for the button
        self.port_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # Allow the button to expand horizontally
        layout.addWidget(self.port_button, 4, 7)

        # Add the upload button in the bottom right of the application with any necessary spacers between it and the other buttons
        layout.addItem(QSpacerItem(40, 20), 5, 0)
        layout.addItem(QSpacerItem(20, 40), 6, 0)
        layout.addItem(QSpacerItem(20, 40), 7, 0)
        layout.addItem(QSpacerItem(20, 40), 8, 0)

        layout.addWidget(self.upload_btn, 9, 7, 1, 1)
        self.upload_btn.setMinimumWidth(175)  # Set a minimum width for the button
        layout.setAlignment(self.upload_btn, Qt.AlignRight | Qt.AlignBottom)

        # Page 2 Widgets
        # Add the messages label and box
        layout.addWidget(self.messages_label, 1, 3, 1, 1)  # Messages label
        layout.addWidget(self.messageBox, 2, 3, 10, 10)  # Messages box, increased row span to make it taller

        # Add the back button (it should be in the bottom left of the application)
        layout.addItem(QSpacerItem(40, 20), 13, 0)
        layout.addItem(QSpacerItem(20, 40), 14, 0)

        layout.addWidget(self.back_btn, 15, 3, 1, 1)  # Back button

        # Add the progress bar and on the row above the back button
        layout.addWidget(self.progress_label, 13, 3, 1, 1)
        layout.addWidget(self.progress_bar, 13, 4, 1, 1)

        self.setLayout(layout)  # Ensure the layout is set as the main layout for the widget

        self.setWindowTitle( _APP_NAME + " - " + _APP_VERSION)

        # ---------------------------- Actions/Workers ----------------------------
        # setup our background worker thread ...
        # connect the signals from the background processor to callback
        # methods/slots. This makes it thread safe
        self.sig_message.connect(self.appendMessage)
        self.sig_finished.connect(self.on_finished)
        self.sig_progress.connect(self.on_progress)

        # Create our background worker object, which also will do work in it's
        # own thread.
        self._worker = AUxWorker(self.on_worker_callback)

        # add the actions/commands for this app to the background processing thread.
        # These actions are passed jobs to execute.
        self._worker.add_action(AUxEsptoolDetectFlash(), AUxEsptoolUploadFirmware(), AUxEsptoolResetESP32(), \
                                AUxEsptoolEraseFlash(), AUxRp2UploadRp2(), AUxTeensyUploadTeensy())

    def update_firmware_list(self) -> None:
        """Update the firmware list in GUI."""

        if self.device_button.text() == _AUTO_DETECT_DECORATOR:
            self.on_discover_btn_pressed()
            return
        
        self.firmware_button.items.clear()
        # Add the local firmware option to the list of firmware files
        self.firmware_button.addIconItem(_LOCAL_DECORATOR, "Local firmware file", resource_path("fw_local.png"))

        # Check the currently selected device item and update the firmware list accordingly
        self.firmware_button.setText(_FIRMWARE_CHOICE_DECORATOR)
        currentDevice = self.device_button.text()
        for fw in self.deviceDict[currentDevice]:
            # print("Adding firmware: ", fw.displayName, " for device: ", currentDevice)
            self.firmware_button.addIconItem(fw.displayName, fw.description(), fw.fw_image_path())
    
    def show_user_message(self, message: str, windowTitle: str, warning = False) -> None:
        """Show a message box to the user."""
        msg = QMessageBox()
        if warning:
            msg.setIcon(QMessageBox.Warning)
        else:
            msg.setIcon(QMessageBox.Information)
        msg.setText(message)
        msg.setWindowTitle(windowTitle)
        msg.setStandardButtons(QMessageBox.Ok)
        msg.setDefaultButton(QMessageBox.Ok)
        msg.exec_()

    #--------------------------------------------------------------
    # callback function for the background worker.
    #
    # It is assumed that this method is called by the background thread
    # so signals and used to relay the call to the GUI running on the
    # main thread

    def on_worker_callback(self, *args): #msg_type, arg):

        # need a min of 2 args (id, arg)
        if len(args) < 2:
            self.writeMessage("Invalid parameters from the uploader.")
            return

        msg_type = args[0]
        if msg_type == AUxWorker.TYPE_MESSAGE:
            self.sig_message.emit(args[1])
        elif msg_type == AUxWorker.TYPE_FINISHED:
            # finished takes 3 args - status, job type, and job id
            if len(args) < 4:
                self.writeMessage("Invalid parameters from the uploader.")
                return

            self.sig_finished.emit(args[1], args[2], args[3])
        elif msg_type == AUxWorker.TYPE_PROGRESS:
            self.sig_progress.emit(args[1])
            
    @pyqtSlot(str)
    def appendMessage(self, msg: str) -> None:
        if msg.startswith("\r"):
            self.messageBox.moveCursor(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
            self.messageBox.cut()
            self.messageBox.insertPlainText(msg[1:])
        else:
            self.messageBox.insertPlainText(msg)
        self.messageBox.ensureCursorVisible()
        self.messageBox.repaint()

        if msg.find("Detected flash size: 4MB") >= 0:
            self.flashSize = 4
        elif msg.find("Detected flash size: 8MB") >= 0:
            self.flashSize = 8
        elif msg.find("Detected flash size: 16MB") >= 0:
            self.flashSize = 16
        elif msg.find("Detected flash size: ") >= 0:
            self.flashSize = 0

        macAddrPtr = msg.find("MAC: ")
        if macAddrPtr >= 0:
            self.macAddress = msg[macAddrPtr + len("MAC: "):]

    @pyqtSlot(str)
    def writeMessage(self, msg: str) -> None:
        self.messageBox.moveCursor(QTextCursor.End)
        #self.messageBox.ensureCursorVisible()
        self.messageBox.appendPlainText(msg)
        self.messageBox.ensureCursorVisible()
        self.messageBox.repaint()
        #QApplication.processEvents()

    def cleanup_temp(self) -> None:
        """Clean up the temp directory."""
        try:
            if os.path.exists(_TEMP_DIR):
                shutil.rmtree(_TEMP_DIR)
        except:
            self.writeMessage("Error cleaning up temp directory")
    
    @pyqtSlot(int)
    def on_progress(self, progress: int) -> None:
        self.progress_bar.setValue(progress)

    #--------------------------------------------------------------
    # on_finished()
    #
    #  Slot for sending the "on finished" signal from the background thread
    #
    #  Called when the backgroudn job is finished and includes a status value
    @pyqtSlot(int, str, int)
    def on_finished(self, status, action_type, job_id) -> None:
        
        # If the flash erase is finished, re-enable the UX
        if action_type == AUxEsptoolEraseFlash.ACTION_ID:
            self.writeMessage("Flash erase complete...")
            self.disable_interface(False)

        # If the flash detection is finished, trigger the upload
        if action_type == AUxEsptoolDetectFlash.ACTION_ID:
            self.writeMessage("Flash detection complete. Uploading firmware...")
            self.do_upload()

        # If the upload is finished, trigger a reset
        if action_type == AUxEsptoolUploadFirmware.ACTION_ID:
            self.writeMessage("Firmware upload complete. Resetting ESP32...")
            self.esptool_reset()
            # Clean up the temp directory
            self.cleanup_temp()

        # If the reset is finished, re-enable the UX
        if action_type == AUxEsptoolResetESP32.ACTION_ID:
            self.writeMessage("Reset complete...")
            self.writeMessage("DONE: Firmware file copied to ESP32 device.\n")
            self.disable_interface(False)

        if action_type == AUxRp2UploadRp2.ACTION_ID:
            self.end_upload_with_message("DONE: Firmware file copied to RP2 device.\n")

        if action_type == AUxTeensyUploadTeensy.ACTION_ID:
            self.end_upload_with_message("DONE: Firmware file copied to Teensy device.\n")

    # --------------------------------------------------------------
    # on_port_combobox()
    #
    # Called when the combobox pop-up menu is about to be shown
    #
    # Use this event to dynamically update the displayed ports
    #
    @pyqtSlot()
    def on_port_combobox(self):
        self.update_com_ports()
    
    def update_releases(self) -> list:
        """Update the releases in GUI."""

        # We read the releases from the GitHub API and populate the combobox with the latest release
        releaseNames = []

        try:
            allReleases = requests.get("https://api.github.com/repos/" + _RELEASE_REPO + "/releases")
            # print("RELEASES: ", allReleases.json())
            latestReleaseTime = max([datetime.fromisoformat(rel["published_at"]) for rel in allReleases.json()])
            for rel in allReleases.json():
                if datetime.fromisoformat(rel["published_at"]) == latestReleaseTime:
                    releaseNames.append(rel["tag_name"] + _LATEST_DECORATOR)
                    self.latestRelease = rel["tag_name"]
                else:
                    releaseNames.append(rel["tag_name"]) 
        except:
            # print("Could not get versions from GitHub: Only local firmware upload will be available.\nAre you connected to the internet?")
            self.offline = True
            return

        releaseNames.append(_LOCAL_DECORATOR)
    
    def update_devices_firmware(self):
        # We'll pull the devices by updating our releases and checking the firmware list for the latest release
        self.update_releases()

        # Update firmware list for the latest release
        # print("Looking for latest release: " + self.latestRelease)
        fwFiles = self.get_firmware_list_for_release(self.latestRelease)
        # Now let's populate the device list with the firmware names
        for fwFile in fwFiles:
            if fwFile.device not in self.deviceDict.keys():
                self.deviceDict[fwFile.device] = [fwFile]
            else:
                self.deviceDict[fwFile.device].append(fwFile)
        
        if self.offline:
            # If we are offline, we still need to populate the deivce list, but for each device we will only have the local firmware option
            # print("Offline mode: Only local firmware upload will be available.")  
            # We can populate directly from the manifest if we have it
            for device in _BOARD_MANIFEST.keys():
                if device not in self.deviceDict.keys():
                    # print("Adding device: ", device)
                    self.deviceDict[device] = []
            
            # Open a popup telling the user that we are offline and only local firmware upload is available
            self.show_user_message(message="Could not get versions from GitHub: Only local firmware upload will be available.\nFor latest releases, check your internet connection and restart the app.", 
                                   windowTitle="Offline", warning=True)
        
    def get_device_list(self) -> list:
        self.deviceDict.clear()
        self.update_devices_firmware()
        return list(self.deviceDict.keys())

    def get_basic_firmware_for_device(self, device: str) -> FirmwareFile:
        """
        Get the basic firmware for the device.
        
        If we are offline, we can get a dummy firmware file from the board manifest.
        If we are online, we can get the firmware file from the deviceDict.

        The reason we have both is because we may add boards to a release that are not in the manifest yet.
        """
        # We can get the basic firmware for the device by returning a firmware file  that starts with the basic prefix
        if self.offline:
            board = _BOARD_MANIFEST[device]
            return FirmwareFile.from_file(board["default_fw_name"])

        if device in self.deviceDict:
            for firmware in self.deviceDict[device]:
                if firmware.name.startswith(_BOARD_NAME_PREFIX):
                    return firmware
        
        return None

    def get_firmware_list_for_release(self, release: str) -> list:
        """Get the firmware list for the release."""
        # print("Getting firmware list for release: " + release)
        # We read the releases from the GitHub API and populate the combobox with the latest release
        assetNames = []

        savedFirmware = self.firmwareDict.get(release)
        if savedFirmware is not None:
            # print("Using saved firmware list for release: " + release)
            return savedFirmware
        
        # If we don't have the firmware list saved, we need to get it from GitHub for the first time
        # try:
        req = "https://api.github.com/repos/" + _RELEASE_REPO + "/releases/tags/" + release
        try:
            releaseResponse = requests.get(req, headers={"Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"})
        # print("Headers:", releaseResponse.headers)
        except:
            # print("Could not get versions from GitHub: Only local firmware upload will be available.\nAre you connected to the internet?")
            self.offline = True
            return []
        if releaseResponse.status_code == 403 and "API rate limit exceeded" in releaseResponse.text:
            print ("Maximum GitHub API rate limit exceeded. Please try again later.")
            print ("How many times are you switching between releases? Take a coffee break!")
            print("Headers:", releaseResponse.headers)

        # print("RELEASES: ", releaseResponse.json())
        assets = releaseResponse.json()["assets"]
        # assetNames = [asset["name"] for asset in assets]
        assetNames = [FirmwareFile.from_file(asset["name"]) for asset in assets]
        self.firmwareDict[release] = assetNames # Save the firmware list for this release
        # except:
        #     print("Could not get the firmware for selected release from GitHub. Will use local if available.")
        #     return []
        
        return assetNames
        
    def update_com_ports(self) -> None:
        """Update COM Port list in GUI."""
        self.port_button.items.clear()

        for desc, name, sys in gen_serial_ports():
            # longname = desc + " (" + name + ")"
            # self.port_combobox.addItem(longname, sys)
            self.port_button.addIconItem(name, desc, resource_path("serial_port.png"), sys)

    @property
    def port(self) -> str:
        """Return the current serial port."""
        # Get the sys location from the port button's storedData
        return self.port_button.getStoredData(self.port_button.text())

    @property
    def baudRate(self) -> str:
        """Return the current baud rate."""
        # return str(self.baud_combobox.currentData())
        return "460800" # Only ESP32 cares about baud rate for now and this is a fine one...

    @property
    def theFileName(self) -> str:
        """Return the file name."""
        # Check if the path of the text currently on the firmware button exists meaning local was used
        if os.path.exists(self.firmware_button.text()):
            return self.firmware_button.text()

        for firmware in self.deviceDict[self.device_button.text()]:
            if firmware.displayName == self.firmware_button.text():
                return firmware.name
    
    def theFile(self) -> str:
        """Return the file."""
        # If a local file, just return the file name
        if os.path.exists(self.firmware_button.text()):
            return self.firmware_button.text()
        
        # Otherwise, we need to download the file from GitHub

    @property
    def theDownloadFileName(self) -> str:
        """Return the download file name."""
        # If a local file, just return the file name
        if os.path.exists(self.firmware_button.text()):
             return self.theFileName
        
        return os.path.join(_TEMP_DIR, self.theFileName)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle Close event of the Widget."""
        # shutdown the background worker/stop it so the app exits correctly
        self._worker.shutdown()
        event.accept()

    def open_file_dialog(self) -> None:
        """Open dialog to select bin file."""
        # Here is where we should pull the latest release from GitHub
        options = QFileDialog.Options()
        fileName, _ = QFileDialog.getOpenFileName(
            None,
            "Select Firmware to Upload",
            "",
            "Firmware Files (*.zip *.uf2 *.hex *.elf);;All Files (*)",
            options=options)
        if fileName:
            # self.firmware_combobox.clear()
            # self.firmware_combobox.addItem(fileName, fileName)
            # Add to the firmware button's text and save it to the filename we will actually upload as well...
            self.firmware_button.setText(fileName)

    def on_fw_button_pressed(self) -> None:
        if self.firmware_button.text() == _LOCAL_DECORATOR:
            self.open_file_dialog()

    def on_discover_btn_pressed(self) -> None:
        self.update_com_ports()
        # Assumes that board is already running MicroPython and tries to mpremote to it
        if self.port_button.text() == _PORT_CHOICE_DECORATOR:
            # Open a popup telling the user to first select a port
            self.show_user_message(message="Please select a serial port first before trying auto-detect.", 
                                   windowTitle="Port Not Selected", warning=True)
            return
        
        mpr = self.get_mpremote_session()
        if mpr is not None:
            try:
                boardName = mpr.get_short_board_name()
                if boardName is None:
                    # Let the user know with a popup that we couldn't identify the board name
                    self.show_user_message(message="Could not autodetect the board name. Please select a device and firmware manually.", 
                                        windowTitle="Board Not Identified", warning=True)
                    
                    # mpr.disconnect()
                    return

                self.writeMessage("Identified connected board: " + boardName + "\n")

                # iterate through the deviceDict and check if the board name matches mpHwName for any firmware file
                for device in self.deviceDict.keys():
                    basicFw = self.get_basic_firmware_for_device(device)
                    if basicFw.mpHwName == boardName:
                        self.device_button.setText(device)
                        # Only the "Local" option should ever be available when in offline mode.
                        if not self.offline: 
                            self.firmware_button.setText(basicFw.displayName)

            except Exception as e:
                print(e)
            
        self.writeMessage("Could not identify firmware in latest release matching connected board.\n")

    # TODO: We could possibly instead do this with "QStackedWidgets" which is maybe more "qt-like", but this is quick and easy
    def switch_to_page_one(self) -> None:
        # Hide the page two widgets (Message box and progress bar)
        self.messages_label.hide()
        self.messageBox.hide()
        self.back_btn.hide()
        self.progress_label.hide()
        self.progress_bar.hide()

        # Show the page one widgets (Device, firmware, port, upload button)
        self.device_label.show()
        self.device_button.show()
        self.firmware_label.show()
        self.firmware_button.show()
        self.port_label.show()
        self.port_button.show()
        self.upload_btn.show()
        
    def switch_to_page_two(self) -> None:
        # Hide the page one widgets (Device, firmware, port, upload button)
        self.device_label.hide()
        self.device_button.hide()

        self.firmware_label.hide()
        self.firmware_button.hide()

        self.port_label.hide()
        self.port_button.hide()

        self.upload_btn.hide()

        # Show the page two widgets (Message box and progress bar)
        self.messages_label.show()
        self.messageBox.show()
        self.back_btn.show()
        # self.progress_bar.show()
        # self.progress_label.show()

    #--------------------------------------------------------------
    # disable_interface()
    #
    # Enable/Disable portions of the ux - often used when a job is running
    #
    def disable_interface(self, bDisable=False):
        self.upload_btn.setDisabled(bDisable)
        self.back_btn.setDisabled(bDisable)

    def on_upload_btn_pressed(self) -> None:
        """Get ready to upload the firmware."""
        if (self.device_button.text() == _AUTO_DETECT_DECORATOR ) \
            or (self.device_button.text() == _DEVICE_CHOICE_DECORATOR) \
            or (self.firmware_button.text() == _FIRMWARE_CHOICE_DECORATOR) \
            or (self.port_button.text() == _PORT_CHOICE_DECORATOR):
            # Open a popup window telling user to select a device, firmware, and port
            self.show_user_message(message="Please select a device, firmware, and port before uploading.", 
                                   windowTitle="Upload Error", warning=True)
            return
    
        self.switch_to_page_two()

        # # Only perform the ESPTOOL specific items if we are doing an ESP32 upload
        if not self.theFileName.endswith(".zip"):
            self.disable_interface(True)
            self.do_upload()
            return
        
        portAvailable = False
        for desc, name, sys in gen_serial_ports():
            if (sys == self.port):
                portAvailable = True
        if (portAvailable == False):
            self.writeMessage("Port No Longer Available")
            return

        self.flashSize = 0

        self.writeMessage("Detecting flash size\n\n")

        command = []
        command.extend(["--chip","esp32"])
        command.extend(["--port",self.port])
        command.extend(["--before","default_reset","--after","no_reset"])
        command.extend(["flash_id"])

        # Create a job and add it to the job queue. The worker thread will pick this up and
        # process the job. Can set job values using dictionary syntax, or attribute assignments
        #
        # Note - the job is defined with the ID of the target action
        theJob = AxJob(AUxEsptoolDetectFlash.ACTION_ID, {"command":command})

        # Send the job to the worker to process
        self._worker.add_job(theJob)

        self.disable_interface(True)

    def do_upload_esp32(self, fwFile = None) -> None:
        """Upload the firmware to the ESP32."""
        # Unzip the file to the temp directory
        try:
            with zipfile.ZipFile(fwFile, 'r') as zip_ref:
                zip_ref.extractall(_TEMP_DIR)
        except zipfile.BadZipFile:
            self.end_upload_with_message("Provided ESP32 firmware is of wrong type.")
            return
        
        # Make sure that we now have all three files we need:
        #   - bootloader.bin
        #   - partition-table.bin
        #   - micropython.bin
        # Get the name of the fwFile provided by taking the last part of the path (do this in a cross-platform way with os)
        
        fname = os.path.split(fwFile)[1]
        unzipDir = os.path.join(_TEMP_DIR, fname.replace(".zip",""))
        if not os.path.exists(unzipDir):
            unzipDir = os.path.join(_TEMP_DIR, os.listdir(_TEMP_DIR)[0])
        
        for file in ["bootloader.bin", "partition-table.bin", "micropython.bin"]:
            if not os.path.exists(os.path.join(unzipDir, file)):
                self.end_upload_with_message(f"{os.path.join(unzipDir, file)} not found when checking esp32 zip.")
                return

        # For now we will always assume that the partitions table is 4MB. If future ESP32 devices are released with different flash sizes, we will need to update this code
        # Ideally, we would also add a .txt file with all of the necessary flashing parameters by grepping it from the build output when releases are generated, but for now we'll assume default stuff...
        thePartitionFileName = os.path.join(unzipDir, "partition-table.bin")
        self.flashSize = 4
        theBootloaderFileName = os.path.join(unzipDir, "bootloader.bin")
        theFirmwareFileName = os.path.join(unzipDir, "micropython.bin")

        sleep(1.0) # Don't know why this was here, but hell hath no fury like a sleep removed...
        self.writeMessage("Uploading firmware\n")

        baud = self.baudRate
        if baud == "921600":
            if (platform.system() == "Darwin"): # 921600 fails on MacOS
                self.writeMessage("MacOS detected. Limiting baud to 460800\n")
                baud = "460800"

        command = []
        #command.extend(["--trace"]) # Useful for debugging
        command.extend(["--chip","esp32"])
        command.extend(["--port",self.port])
        command.extend(["--baud",baud])
        command.extend(["--before","default_reset","--after","hard_reset","write_flash","--flash_mode","dio","--flash_freq","40m","--flash_size","4MB"])
        command.extend(["0x1000",theBootloaderFileName])
        command.extend(["0x8000",thePartitionFileName])
        command.extend(["0x10000",theFirmwareFileName])

        #print("python esptool.py %s\n\n" % " ".join(command)) # Useful for debugging - cut and paste into a command prompt

        # Create a job and add it to the job queue. The worker thread will pick this up and
        # process the job. Can set job values using dictionary syntax, or attribute assignments
        #
        # Note - the job is defined with the ID of the target action
        theJob = AxJob(AUxEsptoolUploadFirmware.ACTION_ID, {"command":command})

        # Send the job to the worker to process
        self._worker.add_job(theJob)

        self.disable_interface(True) # Redundant... Interface is still disabled from flash detect
    
    def end_upload_with_message(self, msg: str) -> None:
        """End the upload with a message."""
        self.writeMessage(msg)
        self.cleanup_temp()
        # self.switch_to_page_one()
        self.disable_interface(False)
        self.progress_bar.hide()
        self.progress_label.hide()

    def get_mpremote_session(self) -> MPRemoteSession:
        """Get an mpremote session for the current port."""
        # portName = self.port_combobox.currentText() # This will be something like "USB Serial Device (COM3)" 
        # portName = portName.split("(")[1].split(")")[0].strip() # This will be something like "COM3" and is what mpremote wants
        # print("Port: ", self.port_button.text())

        # check if we are on mac or linux and if so, we need to add the /dev/ prefix to the port name
        if platform.system() == "Darwin" or platform.system().startswith("Linux"):
            portName = "/dev/" + self.port_button.text()
        else:
            portName = self.port_button.text()

        mpr = MPRemoteSession(portName)

        if mpr.validate_session():
            self.writeMessage("MPRemote session validated.\n")
            return mpr
        else:
            self.writeMessage("MPRemote session failed to validate.\n")
            return None

    def do_upload_rp2(self, fwFile = None) -> None:
        """Upload the firmware to the RP2."""
        # We'll simulate the "drag and drop" of the firmware file by copying it to the new drive
        # An alternative would be to use picotool to upload the firmware, but that might be a bit harder to make cross-platform in Python

        # use psutil to discover the disk partitions on host system prior to entering bootloader mode
        oldDrives = psutil.disk_partitions()
        
        # Start an mpremote session for selected port
        mpr = self.get_mpremote_session()

        # If we are able to use mpremote to enter bootloader mode, do so
        # Otherwise, prompt the user to press the correct button sequence to enter bootloader mode
        if mpr is not None:
            self.writeMessage("Able to automatically enter bootloader mode...\n")
            mpr.enter_bootloader()
            self.writeMessage("Entering bootloader mode...\n")
        else:
            self.writeMessage("Unable to automatically enter boot mode...")
            # open a popup window to tell user to press the correct boot button sequence to enter bootloader mode
            bootAnswer = QMessageBox.question(
                self, 'Enter Bootloader', 'Press and hold the "BOOT" button on your board, then press and release the "RESET" button. Finally, release the "BOOT" button, and click "Ok" below. \n\nNOTE: You can ignore the drive popup that your OS will show.',
                QMessageBox.Ok,
                QMessageBox.Cancel
            )

            # Alternative would be to only wait for drive to appear and not ask user to press ok
            # wait for the user to close the popup and wait for the new drive to appear
            if  bootAnswer == QMessageBox.Cancel:
                self.end_upload_with_message("User cancelled bootloader entry, aborting upload.")
                return
            elif bootAnswer == QMessageBox.Ok:
                self.writeMessage("User entered bootloader button sequence. Checking for device in boot mode...\n")
            else:
                self.end_upload_with_message("User did not confirm bootloader entry, aborting upload.")
                return
        
        # wait for the drive to appear and then copy the firmware file to the drive
        newDrives = []
        
        secsWaited = 0

        while len(newDrives) == 0:
            if secsWaited > _MAX_DRIVE_WAIT_SEC:
                self.writeMessage("Did not detect new RP2 drive after entering bootloader mode, aborting upload.")
                self.disable_interface(False)
                return
            sleep(0.01)
            newDrives = [d for d in psutil.disk_partitions() if d not in oldDrives]
            secsWaited += 0.01
        
        self.writeMessage("Detected new RP2 drive: " + newDrives[0].mountpoint + "\n")
        self.writeMessage("Copying firmware file to RP2 device...\n")

        # TODO: we might want a more stringent check here to make sure we have the right drive
        # possibly we could prompt the user to confirm it is the right drive. We might replace this with picotool
        # at some point anyways...

        # We now have the new drive. Copy the firmware file to the new drive

        dest_path = os.path.join(newDrives[0].mountpoint, os.path.split(fwFile)[1])
        theJob = AxJob(AUxRp2UploadRp2.ACTION_ID, {"source": fwFile, "dest": dest_path})

        # Show to progress bar and set it to 0
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.progress_label.show()
        
        self._worker.add_job(theJob)

        self.disable_interface(True)
    
    def do_upload_teensy(self, fwFile = None, boardName = None) -> None:
        bootAnswer = QMessageBox.question(
            self, 'Enter Bootloader', 'Press the reset button on your Teensy board, then click "Ok" below.',
            QMessageBox.Ok,
            QMessageBox.Cancel
        )

        # Alternative would be to only wait for drive to appear and not ask user to press ok
        # wait for the user to close the popup and wait for the new drive to appear
        if  bootAnswer == QMessageBox.Cancel:
            self.end_upload_with_message("User cancelled bootloader entry, aborting upload.")
            return
        elif bootAnswer == QMessageBox.Ok:
            self.writeMessage("User entered bootloader button. Attempting to write firmware...\n")
        else:
            self.end_upload_with_message("User did not confirm bootloader entry, aborting upload.")
            return
            
        # load with the teensy_loader cli
        # We will rename the executables for Linux and MacOs to also have the .exe extension
        # so this works on all platforms.
        # This is b/c Windows is stupid and does not allow us to run bins w/o extensions
        theJob = AxJob(AUxTeensyUploadTeensy.ACTION_ID, {"loader": resource_path("teensy_loader_cli.exe"),
                                                         "mcu":"imxrt1062", 
                                                         "board": boardName,
                                                         "file": fwFile
                                                         })
        
        self._worker.add_job(theJob)

        self.disable_interface(True)

    # Check what type of upload we are doing based on the value in the device button
    # we can use the processor variable in the primary firmware file for the device to determine the type of upload
    # otherwise we can check the file name for the extension
    def is_esp32_upload(self) -> bool:
        """Check if the upload is for ESP32."""
        try:
            # Check the processor variable in the primary firmware file for the device
            return self.get_basic_firmware_for_device(self.device_button.text()).processor == "ESP32"
        except:
            return self.theFileName.endswith(".zip")
    
    def is_rp2_upload(self) -> bool:
        """Check if the upload is for RP2."""
        try:
            # Check the processor variable in the primary firmware file for the device
            return self.get_basic_firmware_for_device(self.device_button.text()).processor == "RP2"
        except:
            return self.theFileName.endswith(".uf2")
    
    def is_teensy_upload(self) -> bool:
        """Check if the upload is for Teensy."""
        try:
            # Check the processor variable in the primary firmware file for the device
            return self.get_basic_firmware_for_device(self.device_button.text()).processor == "Teensy"
        except:
            return self.theFileName.endswith(".elf") or self.theFileName.endswith(".hex")

    def do_upload(self) -> None:
        """Upload the firmware"""
        portAvailable = False
        for desc, name, sys in gen_serial_ports():
            if (sys == self.port):
                portAvailable = True
        if (portAvailable == False):
            self.writeMessage("Port No Longer Available")
            self.disable_interface(False)
            return

        fileExists = False

        # Fetch the file from github if it is not a local file
        # Create the temp directory if it doesn't exist
        if not os.path.exists(_TEMP_DIR):
            os.makedirs(_TEMP_DIR)
        
        # For non-local files, we need to download the file from GitHub
        if not os.path.exists(self.theFileName):
            # Get the latest release from GitHub and check if the file exists
            # try:
            # Example of a download link: https://github.com/sparkfun/micropython/releases/download/v0.0.1/MICROPYTHON_IOTNODE_LORAWAN_RP2350.uf2
            self.writeMessage("Downloading selected firmware from GitHub...\n")
            # req = "https://github.com/sparkfun/micropython/releases/download/" + self.release_combobox.currentText().replace(_LATEST_DECORATOR,"").strip() + "/" + self.theFileName
            try:
                req = "https://github.com/sparkfun/micropython/releases/download/" + self.latestRelease + "/" + self.theFileName
                response = requests.get(req, stream=True)
            except:
                # Open a popup window telling user that we could not download the file or find it locally
                self.show_user_message(message = "Could not download the firmware file from GitHub. Please check your internet connection and try again."
                                  , title = "Download Error", warning = True)
            if response.status_code == 200:
                with open(self.theDownloadFileName, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                fileExists = True
            else:
                self.offline = True
                return
            # except:
            #     self.writeMessage("Failed to download the firmware file from GitHub.")
            #     return
        
        try:
            f = open(self.theDownloadFileName)
            fileExists = True
        except IOError:
            fileExists = False
        finally:
            if (fileExists == False):
                self.writeMessage("File Not Found")
                self.disable_interface(False)
                return
            f.close()

        # Check if which platform we are flashing
        if self.is_rp2_upload():
            self.writeMessage("Preparing to upload RP2 firmware\n")
            self.do_upload_rp2(self.theDownloadFileName)
        elif self.is_esp32_upload():
            if self.flashSize == 0:
                self.writeMessage("Flash size not detected! Defaulting to 16MB\n")
                self.flashSize = 16
            else:
                self.writeMessage("Flash size is " + str(self.flashSize) + "MB\n")

            self.writeMessage("Preparing to upload ESP32 firmware\n")
            self.do_upload_esp32(self.theDownloadFileName)
        elif self.is_teensy_upload():
            self.writeMessage("Preparing to upload Teensy firmware\n")
            board = "TEENSY41" if self.device_button.text() == "Teensy 4.1" else "TEENSY40"
            self.do_upload_teensy(self.theDownloadFileName, board)
        else:
            self.writeMessage("Selected device type is unsupported\n")
            self.disable_interface(False)
            return

    def esptool_reset(self) -> None:
        """Tell the ESP32 to reset/restart"""
        portAvailable = False
        for desc, name, sys in gen_serial_ports():
            if (sys == self.port):
                portAvailable = True
        if (portAvailable == False):
            self.writeMessage("Port No Longer Available")
            self.disable_interface(False)
            return

        sleep(1.0)
        self.writeMessage("Resetting ESP32\n")

        # ---- The esptool method -----

        command = []
        command.extend(["--chip","esp32"])
        command.extend(["--port",self.port])
        command.extend(["--before","default_reset","run"])

        # Create a job and add it to the job queue. The worker thread will pick this up and
        # process the job. Can set job values using dictionary syntax, or attribute assignments
        #
        # Note - the job is defined with the ID of the target action
        theJob = AxJob(AUxEsptoolResetESP32.ACTION_ID, {"command":command})

        # Send the job to the worker to process
        self._worker.add_job(theJob)

        self.disable_interface(True)

class SplitWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setGeometry(300, 300, 1000, 600)
        # self.setAttribute(Qt.WA_DeleteOnClose)  # Ensure proper cleanup on close

        # Create two frame widgets
        frame1 = QFrame(self)
        frame1.setFrameShape(QFrame.StyledPanel)
        frame1.setStyleSheet("background-color: white; border: 0px;")
        frame2 = QFrame(self)
        frame2.setObjectName("Frame2")
        frame2.setFrameShape(QFrame.StyledPanel)
        
        # Add our title banner
        icon = QIcon(resource_path("sfe_flame_large.png"))
        iconLabel = QLabel()
        iconLabel.setPixmap(icon.pixmap(64, 64))
        iconLabel.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        iconLabel.setContentsMargins(15, 0, 0, 0)  # Add some left margin to the icon label
        iconLabel.setStyleSheet("background-color: white;")
        titleLabel = QLabel("SparkFun MicroPython")
        titleLabel.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        titleLabel.setStyleSheet("background-color: white; color: black; font-size: 42px; font-weight: bold;")
        titleLabel.setContentsMargins(-10, 0, 0, 0)  # Add some left margin to the title label

        # show the icon and title in the top left of frame1
        titleLayout = QHBoxLayout()
        titleLayout.setContentsMargins(0, 0, 0, 0)
        titleLayout.addWidget(iconLabel)
        titleLayout.addWidget(titleLabel)
        titleLayout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        frame1.setLayout(titleLayout)

        # Put our main widget in the second frame
        self.mainWidget = MainWidget()
        self.mainWidget.setObjectName("MainWidget")
        self.mainWidget.show()
        self.mainWidget.setParent(frame2)  # Set the parent of the main widget to be frame2
        self.mainWidget.setGeometry(0, 0, frame2.width(), frame2.height())  # Set the geometry of the main widget to be the same as frame2

        # Create a vertical layout
        vbox = QVBoxLayout()
        vbox.setSpacing(0)
        vbox.setContentsMargins(0, 0, 0, 0)
        
        # Add frames with stretch factors
        vbox.addWidget(frame1, 1)  # Frame1 gets a stretch factor of 1
        vbox.addWidget(frame2, 3)  # Frame2 gets a stretch factor of 3
        
        # Set the layout for the window
        self.setLayout(vbox)

    def closeEvent(self, event):
        """Ensure the entire application exits when the window is closed."""
        self.mainWidget.closeEvent(event)
        super().closeEvent(event)

def startUploaderGUI():
    """Start the GUI"""
    from sys import exit as sysExit
    app = QApplication([])
    app.setOrganizationName('SparkFun Electronics')
    app.setApplicationName(_APP_NAME + ' - v' + _APP_VERSION)
    with open(resource_path("qt_style.qss"), "r") as f:
        style = f.read()
    # print("Style:", style)
    app.setStyleSheet(style)
    icon = QIcon(resource_path("sfe_flame.png"))
    app.setWindowIcon(icon)
    app.setApplicationVersion(_APP_VERSION)
    w = SplitWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    startUploaderGUI()