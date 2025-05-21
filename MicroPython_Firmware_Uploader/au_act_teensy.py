from .au_action import AxAction, AxJob
import shutil
from os import system, set_blocking
import subprocess
import sys
from time import perf_counter
import select

class TeensyProgress(object):
    """Class to keep track of the Teensy progress."""
    # See https://github.com/PaulStoffregen/teensy_loader_cli/blob/master/teensy_loader_cli.c
    # a "." character is printed for every block of data written to the teensy. For TEENSY4.0 andd TEENSY4.1 a block is 1024
    kTeensyBlockSize = 1024 
    # This is the maximum time we will wait to receive the "Programming" message from the teensy loader
    # before setting the timeout flag
    # TODO: What is the absolute minimum times we can have here? This was arbitrary...
    kMaximumWaitForBootloader = 5 # seconds

    def __init__(self) -> None:
        self.progSeen = False
        self.dotsWritten = 0
        self.currentMessage = ""
        self.percent = 0
        self.size = 0
        self.startTime = None
        self.timeout = False

    def reset(self, size = 0) -> None:
        """Reset the Teensy progress."""
        self.progSeen = False
        self.dotsWritten = 0
        self.currentMessage = ""
        self.percent = 0
        self.size = size
        self.timeout = False
        # Create a new start time
        self.startTime = perf_counter()
    
    def elapsed_time(self) -> float:
        """Get the elapsed time since the start time."""
        if self.startTime is None:
            return 0
        
        return perf_counter() - self.startTime

    def check_timeout(self) -> bool:
        """Check if the Teensy progress has timed out."""
        if self.startTime is None:
            return False

        elapsed_time = self.elapsed_time()
        if (elapsed_time > self.kMaximumWaitForBootloader) and not self.progSeen:
            self.timeout = True
            return True

        return False

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
        
        else:
            # If we haven't seen the "Programming" message yet, we need to check against our start time to see if we should time out
            if self.check_timeout():
                self.percent = 0

        return self.percent

class AUxTeensyUploadTeensy(AxAction):
    ACTION_ID = "upload-teensy"
    NAME = "Teensy Upload"

    def __init__(self) -> None:
        super().__init__(self.ACTION_ID, self.NAME)
        self.report_progress = None
        self.__teensy_prog = TeensyProgress()

    def run_job(self, job:AxJob, **kwargs):
        self.report_progress = kwargs["worker_cb"]

        self.__teensy_prog.reset(job.size)
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
        
        while not self.__teensy_prog.timeout:
            # Until we are programming, we can use communicate to get the output with a timeout
            if not self.__teensy_prog.progSeen:
                # NOTE: THIS REQUIRES PYTHON 3.12+ ON WINDOWS OR 3.5+ ON UNIX-LIKE
                set_blocking(teensy_proc.stdout.fileno(), False)  # Set the stdout to non-blocking
                
                # Read a chunk of output (polling, since select.select does not work with pipes on Windows)
                output = teensy_proc.stdout.read(1024)
                
                # Feed output to the progress class and to the console
                if output:
                    sys.stdout.write(output.decode())
                    sys.stdout.flush()
                    # Also feed the output to the progress class
                    self.__teensy_prog.parse_message(output.decode())
                
                # If we have timed out waiting for the bootloader, we need to break out of the loop
                if self.__teensy_prog.check_timeout():
                    # Kill the process
                    teensy_proc.kill()
                    self.report_progress(-1)  # Report -1 to indicate a timeout
                    sys.stdout.write("\nTeensy Upload Error: Timed Out...\n")
                    sys.stdout.flush()
                    break
                
            if self.__teensy_prog.progSeen:
                # Now, make read blocking again (Likely not necessary, but it's how I thought about it originally)
                set_blocking(teensy_proc.stdout.fileno(), True)
                # After we see the "Programming" message, we need to read the output one character at a time
                # to get the progress percentage and display interactive content to the user with blocking reads and writes
                output = teensy_proc.stdout.read(1)  # Read a single character
                if teensy_proc.poll() is not None and not output:
                    break
                if output:
                    sys.stdout.write(output.decode())  # Write the character to stdout
                    sys.stdout.flush()  # Ensure it appears immediately
                    # Also feed the output to the progress class
                    percent = self.__teensy_prog.parse_message(output.decode())
                    if percent > 0 and percent < 100:
                        self.report_progress(percent)

        teensy_proc.wait()
        print("\nTeensy Upload Done.\n")
