import gdb
import sys
import os
import subprocess
import weakref
from datetime import datetime
from pathlib import Path

logFile = "stdout"

class LogFile(gdb.Command):
    """Print or set target file to store log entries. It is possible to set to stdout"""
    def __init__(self):
        super(LogFile, self).__init__("logfile", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        global logFile
        if not arg:
            gdb.write('Log file name is {}'.format(logFile))
            return
        if (arg == "stdout") or (arg == "none"):
            logFile = arg
        else:
            Path(logFile).touch(mode=0o666, exist_ok=True)
            logFile = arg
        gdb.write('Log file name set to {}'.format(logFile))

LogFile()

class GetThreadName(gdb.Command):
    """Print the current thead name, if none is set, then the thread id"""
    def __init__(self):
        super(GetThreadName, self).__init__("getthreadname", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if arg:
            raise Exception("This command takes no arguments")
        thread = gdb.selected_thread()
        if not (thread is None):
            threadName = str(thread.name)
            if not threadName:
                (pid, lwpid, tid) = thread.ptid
                if tid == 0:
                    threadName =str(lwpid)
                else:
                    threadName =str(tid)
            gdb.write(threadName)
        else:
            gdb.write('<unknown>')

GetThreadName()

def frameToString(frame):
    if (frame is None) or (not frame.is_valid()):
        return '<unknown>'
    locSpec = ''
    func = frame.function()
    if func is None:
        hexSize = 8 if sys.maxsize > 2**32 else 4
        locSpec = '{0:#0{1}x}'.format(frame.pc(), hexSize + 2)
    else:
        sl = frame.find_sal()
        if sl is None:
            locSpec = os.path.basename(sl.symtab.filename)
        else:
            locSpec = '{}:{}'.format(os.path.basename(sl.symtab.filename), str(sl.line))
    return locSpec

class GetLocSpec(gdb.Command):
    """Print the simplified current frame's file base name and line"""
    def __init__(self):
        super(GetLocSpec, self).__init__("getlocspec", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if arg:
            raise Exception("This command takes no arguments")
        frame = gdb.selected_frame()        
        locSpec = frameToString(frame)
        gdb.write(locSpec)

GetLocSpec()

class GetSimpleBt(gdb.Command):
    """Print the simplified backtrace, just file base names"""
    def __init__(self):
        super(GetSimpleBt, self).__init__("getsimplebt", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if arg:
            raise Exception("This command takes no arguments")
        frame = gdb.selected_frame()
        if (frame is None) or (not frame.is_valid()):
            gdb.write('<unknown>')
            return
        simpleBt = ''
        while not (frame is None):
            simpleBt += frameToString(frame) + ';'
            frame = frame.older()
        gdb.write(simpleBt)

GetSimpleBt()

class GetFormatTime(gdb.Command):
    """Print the current timestamp using a custom format as defined by the strftime routine, pass the desired format as argument"""
    def __init__(self):
        super(GetFormatTime, self).__init__("getformattime", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if not arg:
            raise Exception("This command requires one argument")
        gdb.write(datetime.now().strftime(arg))

GetFormatTime()

class SubprocExec(gdb.Command):
    """Execute command in subprocess and capture output, built-in GDB shell does not capture the output when running on python"""
    def __init__(self):
        super(SubprocExec, self).__init__("subprocexec", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):        
        gdb.write(subprocess.check_output(gdb.string_to_argv(arg)).decode())

SubprocExec()

class Log(gdb.Breakpoint):
    """
    Python Breakpoint extension for "tracepoints", breakpoints that do not stop the inferior
    """
    @staticmethod
    def generateLog(mess, exprs):
        out = []
        for expr in exprs:
            out.append(gdb.execute(expr, False, True))
        outStr = mess.format(*out).replace('\n', '')
        return outStr

    """
    A breakpoint that does not stop the inferior and outputs a user-defined message to a file
    """
    def initInstances():
        # restore all definitions in case we are re-sourcing the file
        if Log.instances is not None:
            return Log.instances
        return []

    instances = initInstances()
    def __init__(self, spec, **kwargs):
        """
        The underlying breakpoint is always internal
        """
        kwargs['internal'] = True
        super(Log, self).__init__(spec, **kwargs)
        self.__class__.instances.append(weakref.proxy(self))

    def stop(self):
        """
        Do not stop (always return false) and store log entry in log file
        """
        global logFile
        if not logFile or logFile == "none":
            return False
        # generate log message
        outStr = Log.generateLog(self.mMess, self.mExprs)
        if logFile == "stdout":
            gdb.write(outStr)
        else:
            with open(logFile, 'a') as openedFileForAppend:
                openedFileForAppend.write(outStr + '\n')
        return False

class TestLog(gdb.Command):
    """Tests the log generation with the given message at the current frame"""
    def __init__(self):
        super(TestLog, self).__init__("testlog", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if not arg:
            raise Exception("Missing arguments")
        # some basic validation
        args = gdb.string_to_argv(arg)
        nargs = len(args)
        if nargs < 1:
            raise Exception("Not enough arguments")
        mess = args[0]
        if mess.count("{}") is not (nargs - 1):
            raise Exception("Invalid message format")
        exprs = args[1:]
        # generate log message
        outStr = Log.generateLog(mess, exprs)
        # print to stdout regardless
        gdb.write(outStr)
        global logFile
        if logFile and not (logFile == "none") and not (logFile == "stdout"):
            with open(logFile, 'a') as openedFileForAppend:
                openedFileForAppend.write(outStr + '\n')

TestLog()

class AddLog(gdb.Command):
    """Add log entry at spec with the given message"""
    def __init__(self):
        super(AddLog, self).__init__("addlog", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if not arg:
            raise Exception("Missing arguments")
        # some basic validation
        args = gdb.string_to_argv(arg)
        nargs = len(args)
        if nargs < 2:
            raise Exception("Not enough arguments")
        spec = args[0]
        mess = args[1]
        if mess.count("{}") is not (nargs - 2):
            raise Exception("Invalid message format")
        kwargs = {}
        log = Log(spec, **kwargs)
        log.mMess = mess
        log.mExprs = args[2:]

AddLog()

class ImportLogs(gdb.Command):
    """Import log definitions from the given file argument (as exported by the exportlogs command). 
    Also supports importing breakpoint definitions passing a default message for as a second argument"""
    def __init__(self):
        super(ImportLogs, self).__init__("importlogs", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if not arg:
            raise Exception("Missing arguments")
        args = gdb.string_to_argv(arg)
        nargs = len(args)
        filename = args[0]
        if not os.path.isfile(filename):
            raise Exception("First argument is not a valid file path or file does not exist")
        kwargs = {}
        if nargs == 1:
            # import from log definitions
            gdb.execute("source {}".format(filename))
        else:
            # import from breakpoint definitions
            sizeOfToken = len("break ")
            mess = args[1]
            exprs = args[2:]
            with open(filename) as file:
                for line in file:
                    breakDef = line.rstrip()
                    if not breakDef.startswith("break "):
                        continue
                    spec = breakDef[sizeOfToken:]                    
                    log = Log(spec, **kwargs)
                    log.mMess = mess
                    log.mExprs = exprs


ImportLogs()

class ExportLogs(gdb.Command):
    """Export log definitions to a file that can be used later with the importlogs command"""
    def __init__(self):
        super(ExportLogs, self).__init__("exportlogs", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if not arg:
            raise Exception("Missing arguments")
        filename = arg
        Path(filename).touch(mode=0o666, exist_ok=True)
        with open(filename, 'a') as openedFileForAppend:            
            for log in Log.instances:
                openedFileForAppend.write("addlog {} \"{}\"".format(log.location, log.mMess))
                for expr in log.mExprs:
                    openedFileForAppend.write(" \"{}\"".format(expr))
                openedFileForAppend.write('\n')

ExportLogs()

class ListLogs(gdb.Command):
    """List log definitions"""
    def __init__(self):
        super(ListLogs, self).__init__("listlogs", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if arg:
            raise Exception("This command takes no arguments")
        if len(Log.instances) == 0:
            gdb.write("No log definitions")
            return
        gdb.write("Num   Location   Message\n")
        for i, log in enumerate(Log.instances):
            try:
                gdb.write("{}      {}    {}\n".format(i, log.location, log.mMess))
            except ReferenceError:
                pass

ListLogs()

class RmLog(gdb.Command):
    """Remove log definition by index (from listlogs list)"""
    def __init__(self):
        super(RmLog, self).__init__("rmlog", gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        # delete all if no args
        if not arg:
            for log in Log.instances:
                log.delete()
            Log.instances = []
            return
        i = int(arg)
        if i < 0 or i >= len(Log.instances):
            raise Exception("Log index out of bounds")
        toRemove = Log.instances[i]
        toRemove.delete()

RmLog()