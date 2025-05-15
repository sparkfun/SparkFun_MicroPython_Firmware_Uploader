SparkFun MicroPython Firmware Uploader
========================================

![MicroPython Uploader](images/MicroPython_Uploader_Windows_1.png)

The MicroPython Firmware Uploader is a simple, easy to use method for updating the firmware on SparkFun MicroPython products. Available on all major platforms (Linux, Mac, Windows), as well as a Python package, the Uploader simplifies working with SparkFun MicroPython products. 

# Contents

* [Notes](#notes)
* [Using the MicroPython Firmware Uploader](#using-the-MicroPython-firmware-uploader)
    * [Upload Firmware](#upload-firmware)
* [Installation](#installation)
    * [Windows Installation](#windows)
    * [macOS Installation](#macos)
        * [Install the CH340 USB drivers](#install-the-ch340-usb-drivers)
        * [Download and install the MicroPython Uploader](#download-and-install-the-MicroPython-uploader)
        * [Launch the MicroPython Uploader application](#launch-the-MicroPython-uploader-application)
    * [Linux Installation](#linux)
    * [Python Package](#python-package)
        * [Raspberry Pi](#raspberry-pi)

# Using the MicroPython Firmware Uploader
  
## Upload Firmware
  
* Attach the MicroPython product over USB
* Click the ```CHOOSE PORT``` button and select the correct COM port from the popup menu.

![Select COM Port](images/MicroPython_Uploader_Windows_2.png)

* Click the ```CHOOSE DEVICE``` button and select the correct SparkFun board from the popup menu. If your board is already running MicroPython and you select ```Auto Detect``` the button should automatically resolve to the correct board. If you select `Auto Detect` and the button populates with the text "Auto Detect" instead of resolving to a board name, Auto Detect was unsuccessful and you must manually select your board. 

![Select Device](images/MicroPython_Uploader_Windows_3.png)

* Click ```CHOOSE FIRMWARE``` and select the firmware file you'd like to upload. Select "Local" if you wish to upload an arbitrary local firmware file from your file system. Otherwise, options will be populated with all the available firmware files for your board from the most recent release in GitHub. Note: Only the local option is available if you are without an internet connection.

![Select Firmware](images/MicroPython_Uploader_Windows_4.png)

* Click the  ```Upload``` button to update the firmware
* Make sure you approve any permission requests for your OS as they appear.
* If necessary (RP2 and Teensy platforms), follow the popup instructions provided to press physical buttons on your device to enter bootloader mode. NOTE: Make sure you are NOT in bootloader mode prior to clicking the `Upload` button. Your board needs to be enumerated as a serial port at the start of the upload.

![Bootloader](images/MicroPython_Uploader_Windows_5.png)


The selected firmware is then uploaded to the connected SparkFun MicroPython product. Upload information and progress are displayed in the `Upload Status` portion of the interface. 

![Firmware Upload](images/MicroPython_Uploader_Windows.gif)

# Installation

Installation binaries are available for all major platforms (macOS, Window, and Linux) on the release page of the MicroPython Uploader GitHub repository:

[**MicroPython Uploader Release Page**](https://github.com/sparkfun/SparkFun_MicroPython_Firmware_Uploader/releases)

Click the arrow next to **Assets** if required to see the installers:

![Releases Assets](images/MicroPython_Uploader_Windows_Install_0.png)


## Windows

* Download the [github release](https://github.com/sparkfun/SparkFun_MicroPython_Firmware_Uploader/releases) zip file - *MicroPythonUploader.win.zip*

![Windows Installation Step 1](images/MicroPython_Uploader_Windows_Install_1.png)

* Right-click the *MicroPythonUploader.win.zip* and select "Extract All" to unzip it

![Windows Installation Step 2](images/MicroPython_Uploader_Windows_Install_2.png)

* This results in the application executable, *MicroPythonUploader.exe*

![Windows Installation Step 3](images/MicroPython_Uploader_Windows_Install_3.png)

* Double-click *MicroPythonUploader.exe* to start the application
* The executable isn't signed, so you will see a *Windows protected your PC* warning

![Windows Installation Step 4](images/MicroPython_Uploader_Windows_Install_4.png)

* Click *More info* and *Run anyway* to run the executable

![Windows Installation Step 5](images/MicroPython_Uploader_Windows_Install_5.png)

## macOS

### Install the CH340 USB drivers

Before you begin, check you have drivers for the CH340 USB interface chip installed:

* Full instructions can be found in our [CH340 Tutorial](https://learn.sparkfun.com/tutorials/how-to-install-ch340-drivers/all#mac-osx)
* Here is a link to the WCH downloads page for the [CH340 / CH341 macOS driver](https://www.wch-ic.com/downloads/CH341SER_MAC_ZIP.html)
* The Zip file contains more instructions: CH34X_DRV_INSTAL_INSTRUCTIONS.pdf

### Download and install the MicroPython Uploader

To download and install the MicroPython Uploader:

* Download the [github release](https://github.com/sparkfun/SparkFun_MicroPython_Firmware_Uploader/releases) file - *MicroPythonUploader.dmg*

![macOS Installation Step 1](images/MicroPython_Uploader_macOS_Install_1.png)

* Click on the Downloads icon, then double-click the *MicroPythonUploader.dmg* file that you downloaded to mount the disk image.

* A Finder window, with the contents of the file will open

* Install the *MicroPythonUploader.app* by dragging it onto the *Applications* folder

![macOS Installation Step 4](images/MicroPython_Uploader_macOS_Install_4.gif)

* Unmount the MicroPythonUploader disk image by opening Finder and ejecting it

![macOS Installation Step 5](images/MicroPython_Uploader_macOS_Install_5.png)

### Launch the MicroPython Uploader application

To launch the MicroPython Uploader application:

* Double-click MicroPythonUploader.app to launch the application

![macOS Installation Step 6](images/MicroPython_Uploader_macOS_Install_6.png)

* The MicroPythonUploader.app isn't signed, so macOS won't run the application, and will display a warning dialog. Click **Done**

![macOS Installation Step 7](images/MicroPython_Uploader_macOS_Install_7.png)

* To approve app execution bring up the macOS *System Settings* and navigate to *Privacy & Security*
* On this page, select the *Open Anyway* button to launch the MicroPythonUploader application

![macOS Installation Step 8](images/MicroPython_Uploader_macOS_Install_8.png)

* Once selected, macOS will present one last dialog. Select **Open Anyway** to run the application

![macOS Installation Step 9](images/MicroPython_Uploader_macOS_Install_9.png)

* Enter your password and click OK. The MicroPythonUploader will now start

## Linux

* Download the [github release](https://github.com/sparkfun/SparkFun_MicroPython_Firmware_Uploader/releases) file - *MicroPythonUploader.linux.gz*
* Un-gzip the file, either by double-clicking in on the desktop, or using the `gunzip` command in a terminal window. This results in the file *MicroPythonUploader* 
* To run the application, the file must have *execute* permission. This is performed by selecting *Properties* from the file right-click menu, and then selecting permissions. You can also change permissions using the `chmod` command in a terminal window
* Once the application has execute permission, you can start the application a terminal window. Change directory's to the application location and issue `./MicroPythonUploader`
* You may need to install drivers for the CH340 USB interface chip. Full instructions can be found in our [CH340 Tutorial](https://learn.sparkfun.com/tutorials/how-to-install-ch340-drivers/all#linux)

## Python Package

The MicroPython Firmware Uploader is also provided as an installable Python package. This is advantageous for platforms that lack a pre-compiled application. 

To install the Python package:
* Download the package file - *python-install-package.zip*
* Unzip the github release file. This results in the installable Python package file - *MicroPython_Firmware_Uploader-1.6.0.tar.gz* (note - the version number might vary)

At a command line - issue the package install command:

* `pip install MicroPython_Firmware_Uploader-1.6.0.tar.gz`
* Once installed, you can start the MicroPython Uploader App by issuing the command `./MicroPython_Formware_Upload` at the command line. (To see the command, you might need to start a new terminal, or issue a command like `rehash` depending on your platform/shell)

Notes:
* A path might be needed to specify the install file location.
* Depending on your platform, this command might need to be run as admin/root
* Depending on your system, you might need to use the command `pip3`
