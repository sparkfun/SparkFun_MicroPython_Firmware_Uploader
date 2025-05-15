"""
This is a Python3 PyQt5 firmware upload GUI for SparkFun MicroPython devices.

MIT license

Please see the LICENSE.md for more details

"""

# Local imports
from .au_worker import AUxWorker
from .au_action import AxJob
from .au_act_esptool import AUxEsptoolDetectFlash, AUxEsptoolUploadFirmware, AUxEsptoolResetESP32, \
    AUxEsptoolEraseFlash
from .mpremote_utils import MPRemoteSession
from .au_act_rp2 import AUxRp2UploadRp2
from .au_act_teensy import AUxTeensyUploadTeensy, TeensyProgress
from .pyqt_utils import PopupListButton
from .firmware_utils import FirmwareFile, resource_path, GithubFirmware

# Standard Python imports
import sys
import os
import os.path
import platform
from time import sleep
from typing import Iterator, Tuple
import zipfile
import shutil
import psutil

# PyQt5 imports
from PyQt5.QtCore import  Qt,  pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QWidget, QLabel,  QGridLayout, \
    QPushButton, QApplication, QFileDialog, QPlainTextEdit, \
    QMessageBox, QVBoxLayout, QProgressBar, QHBoxLayout, QFrame, \
    QSpacerItem, QSizePolicy
from PyQt5.QtGui import QCloseEvent, QTextCursor, QIcon, QFont
from PyQt5.QtSerialPort import  QSerialPortInfo

_APP_NAME = "SparkFun MicroPython Firmware Uploader"

# sub folder for our resource files
_RESOURCE_DIRECTORY = "resource"

# JSON file containing the board manifest
_BOARD_MANIFEST_FILE = "board_manifest.json"

# Repository to check for releases
_RELEASE_REPO = "sparkfun/micropython"

# This is the string for selections of a local firmware file
_LOCAL_DECORATOR = "Local"

# This is the string that will be used to represent board auto detection
_AUTO_DETECT_DECORATOR = "Auto Detect"

# The messages to be displayed in the GUI for the buttons
_DEVICE_CHOICE_DECORATOR = "CHOOSE DEVICE"
_FIRMWARE_CHOICE_DECORATOR = "CHOOSE FIRMWARE"
_PORT_CHOICE_DECORATOR = "CHOOSE PORT"

# Temporary directory for storing the firmware files
_TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")

# Maximum amount of time to wait for a new drive to be mounted after user says they have pressed the boot button
_MAX_DRIVE_WAIT_SEC = 2.0

def get_version(rel_path: str) -> str:
    try: 
        with open(resource_path(rel_path, _RESOURCE_DIRECTORY), encoding='utf-8') as fp:
            for line in fp.read().splitlines():
                if line.startswith("__version__"):
                    delim = '"' if '"' in line else "'"
                    return line.split(delim)[1]
            raise RuntimeError("Unable to find version string.")
    except:
        raise RuntimeError("Unable to find _version.py.")

_APP_VERSION = get_version("_version.py")

def gen_serial_ports() -> Iterator[Tuple[str, str, str]]:
    """Return all available serial ports."""
    ports = QSerialPortInfo.availablePorts()
    return ((p.description(), p.portName(), p.systemLocation()) for p in ports)

class MainWidget(QWidget):
    """Main Widget."""

    sig_message = pyqtSignal(str)
    sig_finished = pyqtSignal(int, str, int)
    sig_progress = pyqtSignal(int)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)

        # ---------------------------- Variables/Objects ------------------
        self.flashSize = 0

        self.teensyProgress = TeensyProgress() # Progress tracking for Teensy uploads. Its done in a different way for ESP32 and RP2...

        self.githubFirmware = GithubFirmware(_RELEASE_REPO, _BOARD_MANIFEST_FILE, _RESOURCE_DIRECTORY)

        if self.githubFirmware.offline:
            # Create a message box to inform the user that they are offline before loading into the app
            self.show_user_message(message="Could not successfully pull the latest firmware release from the internet so you will only be able to flash local firmware. " + \
            "You can find releases here: " "https://github.com/" + _RELEASE_REPO + "/releases. Or flash with your own custom firmware.",
                                   windowTitle="Offline Mode", warning=True),

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
        self.device_button.addIconItem(_AUTO_DETECT_DECORATOR, "Automatically detect the device", resource_path("auto_detect.png", _RESOURCE_DIRECTORY))
        
        for device, imagePath in self.githubFirmware.get_all_board_image_paths():
            self.device_button.addIconItem(device, "", imagePath)

        # Add the local firmware option to the list of firmware files
        self.firmware_button.addIconItem(_LOCAL_DECORATOR, "Local firmware file", resource_path("fw_local.png", _RESOURCE_DIRECTORY))

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
        self.messageBox.setStyleSheet("QPlainTextEdit { color: black; background-color: white; }")
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
        self.progress_bar.setMaximumWidth(300)  # Set a maximum width for the progress bar
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

        # Add the progress bar and label on the row above the back button
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
        self.firmware_button.addIconItem(_LOCAL_DECORATOR, "Local firmware file", resource_path("fw_local.png", _RESOURCE_DIRECTORY))

        # Check the currently selected device item and update the firmware list accordingly
        self.firmware_button.setText(_FIRMWARE_CHOICE_DECORATOR)
        currentDevice = self.device_button.text()
        for fw in self.githubFirmware.deviceDict[currentDevice]:
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
    
    def parse_esp32_progress(self, msg: str) -> None:
        """Parse the ESP32 progress message."""
        # Check for the progress message format and extract the percentage

        # We don't want the ... (100 %) part of the message that comes first from msgs for writing the bootloader and partition table
        # We'll manually update to 100% when we are done writing the firmware
        percent = 0
        if msg.startswith("Writing at") and msg.find("... (100 %)") == -1:
            # Extract the percentage from the message
            percent_str = msg.split("... (")[1].split("%")[0]
            try:
                percent = int(percent_str.strip())
            except ValueError:
                pass

        # Update the progress bar with the extracted percentage
        if percent > 0 and percent <= 100:
            # Emit the progress signal to update the progress bar in the GUI
            self.sig_progress.emit(percent)
    
    def parse_progress(self, msg: str) -> None:
        """Parse the progress message."""
        if self.is_esp32_upload():
            self.parse_esp32_progress(msg)
        elif self.is_teensy_upload():
            progress = self.teensyProgress.parse_message(msg)
            # update the progress bar with the extracted percentage
            if progress is not None:
                if progress > 0 and progress < 100:
                    # emit the progress signal to update the progress bar in the GUI
                    self.sig_progress.emit(progress)

        # rp2 progress is handled down a few levels while the firmware is being uploaded.
        # this is because it is not a parsing of the output message but rather a manual tracking of the copy progress.

    @pyqtSlot(str)
    def appendMessage(self, msg: str) -> None:
        if msg.startswith("\r"):
            self.messageBox.moveCursor(QTextCursor.StartOfLine, QTextCursor.KeepAnchor)
            self.messageBox.cut()
            self.messageBox.insertPlainText(msg[1:])
            self.parse_progress(msg[1:])
        else:
            self.messageBox.insertPlainText(msg)
            self.parse_progress(msg)
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
   
    def progress_bar_start(self, label) -> None:
        """Start the progress bar."""
        self.progress_bar.setValue(0)
        self.progress_label.setText(label)
        self.progress_label.show()
        self.progress_bar.show()

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
            # Emit a signal to update the progress bar to 100%
            self.sig_progress.emit(100)
            self.writeMessage("DONE: Firmware file copied to ESP32 device.\n")
            self.disable_interface(False)

        if action_type == AUxRp2UploadRp2.ACTION_ID:
            self.end_upload_with_message("DONE: Firmware file copied to RP2 device.\n")

        if action_type == AUxTeensyUploadTeensy.ACTION_ID:
            self.sig_progress.emit(100)
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
    
    def get_current_firmware_file(self) -> FirmwareFile:
        for firmware in self.githubFirmware.deviceDict[self.device_button.text()]:
            if firmware.displayName == self.firmware_button.text():
                return firmware

    def get_current_firmware_file_size(self) -> int:
        try:
            size = self.get_current_firmware_file().size
        except:
            size = 0
        
        return size
        
    def update_com_ports(self) -> None:
        """Update COM Port list in GUI."""
        self.port_button.items.clear()

        for desc, name, sys in gen_serial_ports():
            # longname = desc + " (" + name + ")"
            # self.port_combobox.addItem(longname, sys)
            self.port_button.addIconItem(name, desc, resource_path("serial_port.png", _RESOURCE_DIRECTORY), sys)

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

        for firmware in self.githubFirmware.deviceDict[self.device_button.text()]:
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
                for device in self.githubFirmware.get_device_list():
                    basicFw = self.githubFirmware.get_basic_firmware_for_device(device)
                    if basicFw.mpHwName == boardName:
                        self.device_button.setText(device)
                        # Only the "Local" option should ever be available when in offline mode.
                        if not self.githubFirmware.offline: 
                            self.firmware_button.setText(basicFw.displayName)

            except Exception as e:
                print(e)
        else:
            # Let the user know with a popup that we couldn't identify the board name
            self.show_user_message(message="Could not autodetect the board name. Please select a device and firmware manually.", 
                                   windowTitle="Board Not Identified", warning=True)
            
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
            or (self.firmware_button.text() == _LOCAL_DECORATOR) \
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

        self.progress_bar_start("ESP32 Upload Progress:")

        # Send the job to the worker to process
        self._worker.add_job(theJob)

        self.disable_interface(True) # Redundant... Interface is still disabled from flash detect
    
    def end_upload_with_message(self, msg: str) -> None:
        """End the upload with a message."""
        self.writeMessage(msg)
        self.cleanup_temp()
        # self.switch_to_page_one()
        self.disable_interface(False)
        # self.progress_bar.hide()
        # self.progress_label.hide()

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
            # If we can't validate the session, we should return None or raise an exception
            # but for now we'll just return the session object and let the caller handle it
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
        self.progress_bar_start("RP2 Upload Progress:")

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
        theJob = AxJob(AUxTeensyUploadTeensy.ACTION_ID, {"loader": resource_path("teensy_loader_cli.exe", _RESOURCE_DIRECTORY),
                                                         "mcu":"imxrt1062", 
                                                         "board": boardName,
                                                         "file": fwFile
                                                         })
        
        
        # Show to progress bar and set it to 0. Reset our teensy progress bar and save the file size
        self.teensyProgress.reset(self.get_current_firmware_file_size())
        self.progress_bar_start("Teensy Upload Progress:")

        self._worker.add_job(theJob)

        self.disable_interface(True)

    # Check what type of upload we are doing based on the value in the device button
    # we can use the processor variable in the primary firmware file for the device to determine the type of upload
    # otherwise we can check the file name for the extension
    def is_esp32_upload(self) -> bool:
        """Check if the upload is for ESP32."""
        try:
            # Check the processor variable in the primary firmware file for the device
            return self.githubFirmware.get_basic_firmware_for_device(self.device_button.text()).processor == "ESP32"
        except:
            return self.theFileName.endswith(".zip")
    
    def is_rp2_upload(self) -> bool:
        """Check if the upload is for RP2."""
        try:
            # Check the processor variable in the primary firmware file for the device
            return self.githubFirmware.get_basic_firmware_for_device(self.device_button.text()).processor == "RP2"
        except:
            return self.theFileName.endswith(".uf2")
    
    def is_teensy_upload(self) -> bool:
        """Check if the upload is for Teensy."""
        try:
            # Check the processor variable in the primary firmware file for the device
            return self.githubFirmware.get_basic_firmware_for_device(self.device_button.text()).processor == "Teensy"
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
            self.writeMessage("Downloading selected firmware from GitHub...\n")
            
            res = self.githubFirmware.download_firmware(self.theFileName, self.theDownloadFileName)

            if res == False:
                self.writeMessage("Failed to download the firmware file from GitHub.")
                self.show_user_message(message = "Could not download the firmware file from GitHub. Please check your internet connection and try again."
                                  , windowTitle="Download Error", warning = True)
                return
        
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
        self.setMinimumSize(1000, 600)  # Set reasonable minimum dimensions

        # Create two frame widgets
        frame1 = QFrame(self)
        frame1.setFrameShape(QFrame.StyledPanel)
        frame1.setStyleSheet("background-color: white; border: 0px;")
        frame2 = QFrame(self)
        frame2.setObjectName("Frame2")
        frame2.setFrameShape(QFrame.StyledPanel)
        
        # Add our title banner
        icon = QIcon(resource_path("sfe_flame_large.png", _RESOURCE_DIRECTORY))
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
    with open(resource_path("qt_style.qss", _RESOURCE_DIRECTORY), "r") as f:
        style = f.read()
    # print("Style:", style)
    app.setStyleSheet(style)
    icon = QIcon(resource_path("sfe_flame.png", _RESOURCE_DIRECTORY))
    app.setWindowIcon(icon)
    app.setApplicationVersion(_APP_VERSION)
    w = SplitWindow()
    w.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    startUploaderGUI()