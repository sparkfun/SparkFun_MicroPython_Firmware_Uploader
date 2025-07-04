import setuptools
from codecs import open  # To use a consistent encoding
from os import path, rename, chmod
from platform import system, machine
import subprocess
import sys

# sub folder for our resource files
_RESOURCE_DIRECTORY = "MicroPython_Firmware_Uploader/resource"

#https://stackoverflow.com/a/50914550
def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    base_path = getattr(sys, '_MEIPASS', path.dirname(path.abspath(__file__)))
    return path.join(base_path, _RESOURCE_DIRECTORY, relative_path)

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

here = path.abspath(path.dirname(__file__))

# Get the long description from the relevant file
with open(path.join(here, 'DESCRIPTION.md'), encoding='utf-8') as f:
    long_description = f.read()

# Move the correct teensy loader for the platform to be called "teensy_loader_cli.exe" that will actually get installed with the package
# setup.py actually runs twice when running pip install, so that is why we only rename the file if it exists and is not already renamed

teensy_install_path = resource_path("teensy_loader_cli.exe")

if system() == "Windows":
    print("Windows Platform, installing teensy loader.")
    # Rename the teensy loader for Windows
    teensy_windows_path = resource_path("teensy_loader_cli_windows.exe")
    if path.exists(teensy_windows_path):
        rename(teensy_windows_path, teensy_install_path)
elif system().startswith("Linux"):
    # Already named correctly for Linux
    print("Linux Platform, installing teensy loader.")
    # Ensure the teensy loader is executable
    chmod(teensy_install_path, 0o755)
elif system() == "Darwin":
    print("MacOS Platform, installing teensy loader.")
    # Rename the teensy loader for MacOS
    teensy_macos_path = resource_path("teensy_loader_cli_macos.exe")
    if path.exists(teensy_macos_path):
        rename(teensy_macos_path, teensy_install_path)
    # Ensure the teensy loader is executable
    chmod(teensy_install_path, 0o755)
else:
    print("Unknown OS. Teensy loader will not be supported for this installation.")
    
install_deps = ['darkdetect', 'argparse', 'intelhex', 'esptool', 'mpremote', 'requests', 'psutil']

# Raspberry Pi needs python3-pyqt5 and python3-pyqt5.qtserialport
# which can only be installed with apt-get
if (system() == "Linux") and ((machine() == "armv7l") or (machine() == "aarch64")):
    cmd = ['sudo','apt-get','install','python3-pyqt5','python3-pyqt5.qtserialport']
    subprocess.run(cmd)
else:
    install_deps.append('pyqt5')

setuptools.setup(
    name='MicroPython_Firmware_Uploader',

    # Versions should comply with PEP440.  For a discussion on single-sourcing
    # the version across setup.py and the project code, see
    # http://packaging.python.org/en/latest/tutorial.html#version
    version=_APP_VERSION,

    description='Application to upload firmware to SparkFun MicroPython products',
    long_description=long_description,

    # The project's main homepage.
    url='https://docs.sparkfun.com/SparkFun_MicroPython_Firmware/intro/',

    # Author details
    author='SparkFun Electronics',
    author_email='sales@sparkfun.com',

    project_urls = {
        "Bug Tracker" : "https://github.com/sparkfun/SparkFun_MicroPython_Firmware_Uploader/issues",
        "Repository"   : "https://github.com/sparkfun/SparkFun_MicroPython_Firmware_Uploader"
    },
    # Choose your license
    license='MIT',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Production Stable :: 5',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Topic :: Hardware Development :: Build Tools',

        # Pick your license as you wish (should match "license" above)
        'License :: OSI Approved :: MIT License',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',

    ],

    download_url="https://github.com/sparkfun/SparkFun_MicroPython_Firmware_Uploader/releases",

    # What does your project relate to?
    keywords='Firmware SparkFun MicroPython Uploader',

    # You can just specify the packages manually here if your project is
    # simple. Or you can use find_packages().
    packages=["MicroPython_Firmware_Uploader", "MicroPython_Firmware_Uploader/resource"],

    # List run-time dependencies here.  These will be installed by pip when your
    # project is installed. For an analysis of "install_requires" vs pip's
    # requirements files see:
    # https://packaging.python.org/en/latest/technical.html#install-requires-vs-requirements-files
    install_requires=install_deps,

    # If there are data files included in your packages that need to be
    # installed, specify them here.  If using Python 2.6 or less, then these
    # have to be included in MANIFEST.in as well.
    package_data={
        'MicroPython_Firmware_Uploader/resource': ['*.png', '*.jpg', '*.ico', '*.bin', '*.icns', '*.qss', '*.json', '*.exe'],
    },



    # To provide executable scripts, use entry points in preference to the
    # "scripts" keyword. Entry points provide cross-platform support and allow
    # pip to create the appropriate form of executable for the target platform.
    entry_points={
        'console_scripts': ['MicroPython_Firmware_Upload=MicroPython_Firmware_Uploader:startUploaderGUI',
        ],
    },
)
