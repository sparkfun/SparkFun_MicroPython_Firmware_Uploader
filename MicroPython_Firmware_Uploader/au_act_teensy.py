from .au_action import AxAction, AxJob
import shutil
from os import system
import subprocess
import sys

class AUxTeensyUploadTeensy(AxAction):
    ACTION_ID = "upload-teensy"
    NAME = "Teensy Upload"

    def __init__(self) -> None:
        super().__init__(self.ACTION_ID, self.NAME)
    
    def run_job(self, job:AxJob, **kwargs):
        # Ensure stdout of our subprocess gets routed through our stdout to the wedge thingy and then the UI. 
        # Basic os.system() and subprocess.run() don't do this.

        # Some platforms (Windows) have CREATE_NO_WINDOW, but others (linux) don't. 
        # So we need to check if the flag exists and only use it if it does.
        if hasattr(subprocess, 'CREATE_NO_WINDOW'):
            teensy_proc = subprocess.Popen([job.loader, f"--mcu={job.mcu}", "-v", "-w", job.board, job.file], 
                                            creationflags=subprocess.CREATE_NO_WINDOW,
                                            stdout=subprocess.PIPE, 
                                            stderr=subprocess.PIPE)
        else:
            teensy_proc = subprocess.Popen([job.loader, f"--mcu={job.mcu}", "-v", "-w", job.board, job.file], 
                                            stdout=subprocess.PIPE, 
                                            stderr=subprocess.PIPE)
        
        while True:
            output = teensy_proc.stdout.read(1)  # Read a single character
            if teensy_proc.poll() is not None and not output:
                break
            if output:
                sys.stdout.write(output.decode())  # Write the character to stdout
                sys.stdout.flush()  # Ensure it appears immediately

        teensy_proc.wait()
        print("\nTeensy Upload Done.\n")

class TeensyProgress(object):
    """Class to keep track of the Teensy progress."""
    # See https://github.com/PaulStoffregen/teensy_loader_cli/blob/master/teensy_loader_cli.c
    # a "." character is printed for every block of data written to the teensy. For TEENSY4.0 andd TEENSY4.1 a block is 1024
    kTeensyBlockSize = 1024 

    def __init__(self) -> None:
        self.progSeen = False
        self.dotsWritten = 0
        self.currentMessage = ""
        self.percent = 0
        self.size = 0

    def reset(self, size = 0) -> None:
        """Reset the Teensy progress."""
        self.progSeen = False
        self.dotsWritten = 0
        self.currentMessage = ""
        self.percent = 0
        self.size = size

    def dots_to_percent(self, numDots: int) -> int:
        """Convert the number of dots to a percentage."""
        # To avoid potential devide by zero errors, we need to check if the size is 0
        if self.size == 0:
            return 0

        # Calculate the percentage based on the number of dots written and the size of the firmware file

        # See https://github.com/PaulStoffregen/teensy_loader_cli/blob/master/teensy_loader_cli.c
        # each dot represents a block of data that has been written to the teensy
        # The number of dots is the number of blocks written, so we can calculate the percentage based on the size of the firmware file
        
        # TODO: This isn't shaping up to be super accurate, but is fine for a start to give users some visual feedback as it programs
        # We can always improve this later (maybe digging deeper into the teensy_loader_cli to see bytes/dot or with experimentally determining ~size/dot)
        return int((numDots * TeensyProgress.kTeensyBlockSize) / self.size * 100)

    def parse_message(self, msg: str) -> int:
        self.currentMessage += msg

        if "Programming" in self.currentMessage:
            self.progSeen = True
            self.dotsWritten = 0
            self.currentMessage = self.currentMessage.split("Programming")[1] # Remove the "Programming" part of the message
        
        if self.progSeen:
            # To avoid potential devide by zero errors, we need to check if the size is 0
            if self.size == 0:
                return 0

            self.dotsWritten += self.currentMessage.count(".")
            self.currentMessage = ""
            self.percent = self.dots_to_percent(self.dotsWritten)

        return self.percent
