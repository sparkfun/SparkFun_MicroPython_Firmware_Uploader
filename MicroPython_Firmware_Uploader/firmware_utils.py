import requests
from datetime import datetime
import sys
import os
from json import load

# Can update these if more prefixes/build types are added or if this is used in future projects with different prefixes
_BOARD_NAME_PREFIX = "MICROPYTHON_"

_ALT_NAME_PREFIXES = ["MINIMAL_MICROPYTHON_"]

_DEFAULT_RESOURCE_PATH = "resource"

def strip_alt_prefixes(name: str) -> str:
    """Strip the prefixes from the name."""
    for prefix in _ALT_NAME_PREFIXES:
        name = name.replace(prefix, "")
    
    # Add back in the BOARD_NAME_PREFIX if it is not there
    if not name.startswith(_BOARD_NAME_PREFIX):
        name = _BOARD_NAME_PREFIX + name

    return name

#https://stackoverflow.com/a/50914550
def resource_path( relativePath, basePath = _DEFAULT_RESOURCE_PATH ):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, basePath, relativePath)

# TODO: Should probably make a FirmwareFile base class and then derive from it for a MicroPythonFirmwareFile
# such that this is more extensible for future use...

# This is extensible such that if we release other firmware versions per-board we can update this class
# This class contains the name of the file, the name to display in the GUI, whether the file has qwiic drivers,
# and the processor that we assume it is for
class FirmwareFile(): 
    def __init__(self, name: str, displayName: str, hasQwiic: bool, processor: str, device: str, mpHwName, manifest={}, resourceDir=_DEFAULT_RESOURCE_PATH) -> None:
        self.name = name
        self.displayName = displayName
        self.hasQwiic = hasQwiic
        self.processor = processor
        self.device = device
        self.mpHwName = mpHwName
        self.resourceDir = resourceDir
        self.manifest = manifest
        self.size = 0

    # Alternate constructor that takes the firmware file name and parses it to get the other features
    @classmethod
    def from_file(cls, firmwareFile: str, manifest: dir) -> 'FirmwareFile':
        name = firmwareFile
        device = processor = mpHwName = None
        
        # Try to determine our values from the board manifest
        no_prefix_name = strip_alt_prefixes(name)

        # Find the device in the manifest based on the firmware file name
        for board in manifest.keys():
            if manifest[board]["default_fw_name"] == no_prefix_name:
                device = board
                processor = manifest[board]["processor_type"]
                mpHwName = manifest[board]["micropy_hw_board_name"]

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

        return cls(name, displayName, hasQwiic, processor, device, mpHwName, manifest)

    def board_image_path(self) -> str:
        """Return the path to the image for the firmware file."""
        # we can use the name of this fw file object to find the image name in the manifest
        try:
            image_name = self.manifest[self.device]["image_name"]
            if os.path.exists(resource_path(image_name, self.resourceDir)):
                # print("Found image for: ", self.name)
                return resource_path(image_name, self.resourceDir)
        except:
            #print("Error getting image path for firmware file: ", self.name)
            pass
        
        return resource_path("default_board_img.png", self.resourceDir)
    
    # TODO: In theory, we could make this more dynamic and pull the images down from github
    # from micropython-media repo in boards/board_name, but for now we'll just use the local images
    def fw_image_path(self) -> str:
        """
        Firmware images should be in resource directory with the name fw_<prefix_lower_case>.jpg.
        
        For now we only have two images, but using the same naming convention we can easily add more images.
        """
        for _prefix in _ALT_NAME_PREFIXES:
            if self.name.startswith(_prefix):
                return resource_path("fw_" + _prefix.lower() + ".jpg", self.resourceDir)
        
        return resource_path("fw_" + _BOARD_NAME_PREFIX.lower() + ".jpg", self.resourceDir)

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
"""
This class is used to download firmware from GitHub.

It creates a dictionary that matches release names to dictionaries of firmware files keyed by the device name.

release_name0: { 
    { 
        device_name0: [FirmwareFile0, FirmwareFile1, ...],
        device_name1: [FirmwareFile0, FirmwareFile1, ...],
    }
}
release_name1: ...

The dictionary is created by parsing the GitHub releases page and the firmware files in each release.
"""
class GithubFirmware():
    def __init__(self, url: str, manifestName = "board_manifest.json", resourceDir = "resource") -> None:
        self.url = url
        self.resourceDir = resourceDir
        self.manifestName = manifestName # This is the board manifest that contains information about the boards
        
        self.offline = False
        self.latestRelease = None # Latest release name
        self._currentRelease = None # Set to update internal state such that user's future requests apply to this release
        self.firmwareFiles = {} # Dictionary of firmware files keyed by the device name

        self.manifest = None
        try: 
            with open(resource_path(manifestName, resourceDir), 'r') as f:
                self.manifest = load(f)
        except Exception as e:
            # print("Error loading board manifest: ", e)
            print("No board manifest found, some features disabled.")
            print("Tried to find the manifest in: ", resource_path(manifestName, resourceDir))
            print("Check your installation to make sure that the resource files are included.")
            pass

        self.update_firmware() # Update the firmware files from the GitHub releases page
        
        # It should be easy in the future to set the current release to something else if that 
        # functionality is ever needed.

        # Set the current release to the latest release
        self.set_current_release(self.latestRelease)

    def set_current_release(self, release: str) -> None:
        """Set the current release to the given release name."""
        self._currentRelease = release

    def get_current_device_dict(self) -> dict:
        """Get the current device dictionary."""
        # If we are offline, simply return a dictionary with empty firmware lists for each device
        if self.offline:
            return {board: [] for board in self.manifest.keys()}
            
        if self._currentRelease is None:
            raise ValueError("No current release set.")
        
        return self.firmwareFiles[self._currentRelease]
    
    @property
    def deviceDict(self) -> dict:
        """Get the current device dictionary."""
        return self.get_current_device_dict()

    def get_device_list(self, update = False) -> list:
        """Get the list of devices in the current release."""
        if update:
            self.update_firmware()

        if self.offline:
            # Return the list of devices in the manifest
            return list(self.manifest.keys())
        else:
            if self._currentRelease is None:
                # print("No current release set.")
                return []
            
            return list(self.firmwareFiles[self._currentRelease].keys())
    
    def get_all_board_image_paths(self) -> list:
        """
        Get the list of all board image paths.
        
        returns a list of tuples of the form (board_name, image_path)
        The image path is the path to the image file in the resource directory.
        """
        if self.manifest is None:
            return []

        # Get the list of all board image paths
        imgPaths = []
        for board in self.manifest.keys():
            try:
                imgPath = self.manifest[board]["image_name"]
                if os.path.exists(resource_path(imgPath, self.resourceDir)):
                    imgPaths.append((board, resource_path(imgPath, self.resourceDir)))
            except Exception as e:
                # print("Error getting image path for board: ", board)
                pass
        
        return imgPaths
    
    def get_basic_firmware_for_device(self, device: str) -> FirmwareFile:
        """
        Get the basic firmware for the device.
        
        If we are offline, we can get a dummy firmware file from the board manifest.
        If we are online, we can get the firmware file from the deviceDict.

        The reason we have both is because we may add boards to a release that are not in the manifest yet.
        """
        # We can get the basic firmware for the device by returning a firmware file  that starts with the basic prefix
        if self.offline:
            board = self.manifest[device]
            return FirmwareFile.from_file(board["default_fw_name"], self.manifest)

        if device in self.firmwareFiles[self._currentRelease]:
            for firmware in self.firmwareFiles[self._currentRelease][device]:
                if firmware.name.startswith(_BOARD_NAME_PREFIX):
                    return firmware
        
        return None
    
    def update_firmware(self) -> None:
        """Update the firmware files from the GitHub releases page."""
        try:
            allReleases = requests.get("https://api.github.com/repos/" + self.url + "/releases")
            if allReleases.status_code != 200:
                # print("Error getting releases from GitHub: ", allReleases.status_code)
                self.offline = True
                return

            latestReleaseTime = max([datetime.fromisoformat(rel["published_at"]) for rel in allReleases.json()])

            for release in allReleases.json():
                releaseName = release["tag_name"]
                
                if releaseName not in self.firmwareFiles:
                    self.firmwareFiles[releaseName] = {}
                if datetime.fromisoformat(release["published_at"]) == latestReleaseTime:
                    self.latestRelease = releaseName
                
                for asset in release["assets"]:
                    # Get the device name from the firmware file name
                    try:
                        firmwareFile = FirmwareFile.from_file(asset["name"], self.manifest)
                        firmwareFile.size = asset["size"]
                        firmwareFile.resourceDir = self.resourceDir
                        
                        # Check if the device is in the manifest
                        if firmwareFile.device not in self.firmwareFiles[releaseName]:
                            self.firmwareFiles[releaseName][firmwareFile.device] = [firmwareFile]
                        
                        # Add the firmware file to the list of firmware files for the device
                        else:   
                            self.firmwareFiles[releaseName][firmwareFile.device].append(firmwareFile)
                    except Exception as e:
                        # print("Error getting firmware file from release: ", e)
                        pass
        except:
            self.offline = True
    
    def check_if_in_release(self, fileName: str) -> bool:
        """Check if the firmware file is in the current release."""
        if self._currentRelease is None:
            # print("No current release set.")
            return False
        
        # Check if the file name is in the current release for any device
        for device in self.firmwareFiles[self._currentRelease]:
            for firmware in self.firmwareFiles[self._currentRelease][device]:
                if firmware.name == fileName:
                    return True
        
        return False

    def download_firmware(self, fileName, downloadName):
        """
        Download the firmware file from GitHub.

        fileName: The name of the firmware file to download.
        downloadName: The name to save the firmware file as on the local machine.
        
        returns True if the download was successful, False otherwise.
        """

        if self.offline:
            print("Offline mode, cannot download firmware.")
            return False

        if self._currentRelease is None:
            print("No current release set.")
            return False
        
        if not self.check_if_in_release(fileName):
            print("Firmware file not found in current release.")
            return False
        
        try:
            req = "https://github.com/" + self.url + "/releases/download/" + self._currentRelease + "/" + fileName
            response = requests.get(req, stream=True)

            if response.status_code != 200:
                # print("Error downloading firmware file: ", response.status_code)
                self.offline = True
                return False
        
            with open(downloadName, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        except Exception as e:
            print("Error downloading firmware file: ", e)
            return False
        
        return True