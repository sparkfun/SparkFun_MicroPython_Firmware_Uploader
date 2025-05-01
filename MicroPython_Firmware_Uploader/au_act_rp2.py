from .au_action import AxAction, AxJob
import shutil
from os import stat, symlink, readlink, path

class AUxRp2UploadRp2(AxAction):
    ACTION_ID = "upload-rp2"
    NAME = "RP2 Upload"
    READINTO_BUFSIZE = 1024 * 1024 
    
    def __init__(self) -> None:
        super().__init__(self.ACTION_ID, self.NAME)
        self.report_progress = None
    
    def run_job(self, job:AxJob, **kwargs):
        try:            
            self.report_progress = kwargs["worker_cb"]
            # Assuming the upload function is defined in the same module
            # TODO: This is a bit slow on windows...we might want to optimize the copy
            # copy(job.source, job.dest)
            self.report_progress(5)
            self.custom_shutil_copy(job.source, job.dest, cb_function=self.report_progress)
            # shutil.copy(job.source, job.dest)
            # self.report_progress(100)  # Report 100% progress
        except Exception:
            return 1  # Error occurred
        
        return 0  # Success

    def copyfileobj(self, fsrc, fdst, callback, size=0):
        fsrc_read = fsrc.read
        fdst_write = fdst.write

        length = shutil.COPY_BUFSIZE

        copied = 0
        while True:
            buf = fsrc_read(length)
            if not buf:
                break
            fdst_write(buf)
            copied += len(buf)
            callback(int((copied / size) * 100))

    def custom_shutil_copy(self, src, dst, cb_function=None, follow_symlinks=True):
        """Custom copy function to report progress."""
        if shutil._samefile(src, dst):
            raise shutil.SameFileError("{!r} and {!r} are the same file".format(src, dst))

        for fn in [src, dst]:
            try:
                st = stat(fn)
            except OSError:
                # File most likely does not exist
                pass
            else:
                if shutil.stat.S_ISFIFO(st.st_mode):
                    raise shutil.SpecialFileError("`%s` is a named pipe" % fn)
        if not follow_symlinks and path.islink(src):
            symlink(readlink(src), dst)
        else:
            size = stat(src).st_size
            with open(src, 'rb') as fsrc:
                try:
                    with open(dst, 'wb') as fdst:
                        self.copyfileobj(fsrc, fdst, callback=cb_function, size=size)
                except Exception as e:
                    print("Error: ", e)
                    raise

