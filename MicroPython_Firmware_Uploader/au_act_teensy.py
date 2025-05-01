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
        teensy_proc = subprocess.Popen([job.loader, f"--mcu={job.mcu}", "-v", "-w", job.board, job.file], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        while True:
            output = teensy_proc.stdout.readline()
            if teensy_proc.poll() is not None and not output:
                break
            if output:
                print(output.decode().strip())
                # Here you can also call a callback function to report progress if needed

        teensy_proc.wait()
        print("\nTeensy Upload Done.\n")