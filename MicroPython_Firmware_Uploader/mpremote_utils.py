from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple

from mpremote import commands
from mpremote import main as mpr_main
from mpremote import mip
from serial import SerialException
# import io
# from contextlib import redirect_stdout
import sys
import threading

# TODO: This might not be the best way to do this...
# Was originally necessary because default redirection with redirect_stdout doesn't automatically work with mpremote
# (because it is missing encoding, etc.)
class StdoutCapture:
    def __init__(self):
        self.capturedOutput = ""
        self._originalStdout = sys.stdout
        self.encoding = 'utf-8'
        self.doStrip = False
        self.doMute = True

    def start(self):
        sys.stdout = self

    def write(self, text):
        if self.doStrip:
            text = text.strip()

        self.capturedOutput += text

        if self.doMute:
            return
        
        self._originalStdout.write(text)

    def flush(self):
        self._originalStdout.flush()

    def stop(self):
         sys.stdout = self._originalStdout
        
    def get_output(self):
        return self.capturedOutput
"""
Example usage of MPRemoteArgs (https://stackoverflow.com/questions/76710405/how-to-upload-a-python-file-from-a-python-script):
    # connect to the device
    # device=["/dev/ttyACM0"],
    #
    # execute the string on the device
    # expr=["import micropython; micropython.mem_info()"],
    #
    # evaluate and print the result of a Python expression
    # eval=["1/2"],
    #
    # list all files on the device
    # command=["ls"],
    #
    # copy the file "changelog.md" from the parent dir to the device
    # command=["cp"],
    # path=["../changelog.md", ":changelog.md"],
    #
    # copy the folder "tests" recursively to the device
    # command=["cp"],
    # recursive=True,
    # path=["tests/", ":"],
    #
    # remove the file "changelog.md" from the device
    # command=["rm"],
    # path=["changelog.md"],
    #
    # run given local script
    # do_run_command=True,
    # path=["boot.py"],
    #
    # install some mip package
    # command=["install"],
    # packages=[
    #     "umqtt.simple",
    #     "github:brainelectronics/micropython-modbus",
    # ],
"""
@dataclass
class MPRemoteArgs:
    device: Sequence[str]
    follow: bool = True
    expr: Sequence[str] = field(default_factory=list)
    eval: Sequence[str] = field(default_factory=list)
    recursive: bool = False
    verbose: bool = False
    command: Sequence[str] = field(default_factory=list)
    path: Tuple[str, ...] = field(default_factory=list)
    do_run_command: bool = False
    mpy: bool = True
    target: Optional[str] = None
    index: Optional[str] = None
    packages: Sequence[str] = field(default_factory=list)


class MPRemoteSession:
    def __init__(self, device: str) -> None:
        self.device = device
        self.state = mpr_main.State()
        self.args = MPRemoteArgs(device=[device])
    
    def __del__(self) -> None:
        self.disconnect()

    def connect(self) -> None:
        commands.do_connect(state=self.state, args=self.args)

    def disconnect(self) -> None:
        commands.do_disconnect(self.state)

    def exec_command(self, command: str) -> None:
        self.args.expr = [command]
        commands.do_exec(state=self.state, args=self.args)
    
    def exec_command_with_output(self, command: str, timeout: Optional[float] = 2) -> str:

        self.args.expr = [command]
        capture = StdoutCapture()
        capture.start()

        def execute():
            try:
                commands.do_exec(state=self.state, args=self.args)
            except Exception:
                pass  # Handle any exceptions gracefully

        thread = threading.Thread(target=execute, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            # Attempt to cleanly stop the thread by disconnecting the state
            try:
                commands.do_disconnect(self.state)
            except Exception:
                pass  # Ignore any errors during cleanup

            capture.stop()
            raise TimeoutError("Command execution exceeded the timeout limit.")

        capture.stop()
        return capture.get_output()
    
    def validate_session(self) -> None:
        # Ensure that we can ping the device by checking sys.implementation.name
        # This is a good way to check if the device is connected and responsive
        try:
            if self.is_connected():
                res = self.exec_command_with_output("import sys; print(sys.implementation.name)")
                if res is None:
                    return False
                if res.strip() == "micropython":
                    return True
        except Exception as e:
            #print("Error validating session:", e)
            pass
        
        return False

    
    def eval_command(self, command: str) -> None:
        self.args.expr = self.args.eval = [command]
        commands.do_eval(state=self.state, args=self.args)

    def command(self, command: str) -> None:
        self.args.command = [command]
        commands.do_filesystem(state=self.state, args=self.args)
    
    def run_command(self, path: str) -> None:
        self.args.do_run_command = True
        self.args.path = [path]
        commands.do_run(state=self.state, args=self.args)
    
    def mip_packages(self, packages: Sequence[str]) -> None:
        self.args.packages = packages
        mip.do_mip(state=self.state, args=self.args)

    def get_transport(self) -> str:
        """
        Get the transport type of the device.
        
        Returns the transport type as a string.
        """
        return self.state.transport.__class__.__name__
    
    def is_connected(self) -> bool:
        """
        Check if the device is connected. 
        
        Returns True if connected, False otherwise.
        """
        try:
            commands.do_connect(state=self.state, args=self.args)
            return True
        except:
            return False
        finally:
            commands.do_disconnect(self.state)
    
    def enter_bootloader(self) -> bool:
        """
        Enter the bootloader mode of the device.

        Uses the same expr command as they use in mpremote bootloader command: https://github.com/micropython/micropython/blob/master/tools/mpremote/mpremote/main.py
        """
        try:
            self.connect()
            self.exec_command("import time, machine; time.sleep_ms(100); machine.bootloader()")
        # We expect a serial exception here, as the device is in bootloader mode
        except SerialException as e:
            return True
        except Exception as e:
            return False
    
    def get_board_name(self) -> str:
        """
        Get the board name of the device.
        
        Returns the board name as a string or None if it cannot be determined.
        """
        try:
            return self.exec_command_with_output("import os; print(os.uname().machine)").strip()
        except:
            return None
    
    def get_short_board_name(self) -> str:
        """
        Get the short board name of the device.
        
        Returns the short board name as a string or None if it cannot be determined.
        The short board name is the part of the board name before the "with" keyword.
        So, this does not include the chip name.
        """
        name = self.get_board_name()
        if name is None:
            return None
        if "with" in name:
            return name.split("with")[0].strip()

