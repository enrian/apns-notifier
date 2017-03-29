# -*- Mode: Python -*-
#
# General log emission class
#

import array, inspect, os, sys, traceback, __main__
from time import (strftime, gmtime)

try:
    from thread import get_ident
except:
    from _thread import get_ident

#
# Logger -- general routines for submitting information to a log - syslog or 
# file.
#
class Logger:

    kLevelMap = { 'fatal': 0,
                  'error': 1,
                  'warning': 2,
                  'info': 3,
                  'verbose': 4,
                  'debug': 5 }

    #
    # Define entry and exit tags used by LogProcEntry and LogProcExit
    #
    kEntryTag = 'BEG'
    kExitTag =  'END'

    #
    # Default output to nothing.
    #
    def __init__( self ):
        for name, level in list(self.kLevelMap.items()):
            setattr(self, 'k' + name.capitalize(), level)

        self._out = self._flush = self._close = self._nothing
        self.fd = None                  # File name or descriptor logging to
        self._showTime = 1               # If TRUE, print timestamp
        self._showThread = 0             # If TRUE, print thread ID
        self._showFile = 1               # If TRUE, print defining file name
        self._showFunc = 1               # If TRUE, print function name
        self._showSelf = 1               # If TRUE, print first method arg
        self.maxLength = None
        self.setLevel(self.kError)

    #
    # If logging to a file, close it and reopen it. Used for rolling log files.
    #
    def reset(self):
        if isinstance(self.fd, str):
            self.useFile(self.fd, self._showTime, self._showThread, self._showFile)

    def _log(self, level, logMsg):
        self._out(logMsg)
        self._flush()

    def _fatal(self, *args): self._log(self.kFatal, self._formatOutput(self.kFatal, args))
    def _error(self, *args): self._log(self.kError, self._formatOutput(self.kError, args))
    def _warning(self, *args): self._log(self.kWarning, self._formatOutput(self.kWarning, args))
    def _info(self, *args): self._log(self.kInfo, self._formatOutput(self.kInfo, args))
    def _verbose(self, *args): self._log(self.kVerbose, self._formatOutput(self.kVerbose, args))
    def _debug(self, *args): self._log(self.kDebug, self._formatOutput(self.kDebug, args))
    def _begin(self, *args): self._log(self.kVerbose, self._formatOutput(self.kVerbose, args, self.kEntryTag))
    def _end(self, *args): self._log(self.kVerbose, self._formatOutput(self.kVerbose, args, self.kExitTag))

    #
    # Issues a log message at the given severity level.
    #
    def log(self, level, *args):
        self._log(level, self._formatOutput(level, args))

    #
    # Does not log anything
    #
    def _nothing(self, *ignored):
        return

    #
    # Set the log threshold level. For faster processing, update methods to
    # either emit something or return silently.
    #
    def setLevel(self, maxLevel):
        if isinstance(maxLevel, str):
            tmp = self.kLevelMap.get(maxLevel.lower())
            if tmp is None:
                raise ValueError(maxLevel)
            maxLevel = tmp
 
        if maxLevel > self.kDebug:
            maxLevel = self.kDebug
        elif maxLevel < self.kFatal:
            maxLevel = self.kFatal

        #
        # Turn on/off levels
        #
        procs = self.__class__.__dict__
        for name, level in list(self.kLevelMap.items()):
            if level <= maxLevel:
                setattr(self, name, getattr(self, '_' + name))
            else:
                setattr(self, name, self._nothing)

        #
        # Special handling for entry/exit methods.
        #
        if maxLevel >= self.kVerbose:
            self.begin = self._begin
            self.end = self._end
        else:
            self.begin = self.end = self._nothing

    #
    # Flush any pending output and revert to doing nothing
    #
    def close(self):
        self._flush()
        self._close()
        self._out = self._flush = self._close = self._nothing

    #
    # Setup to use the given file object for log writing
    #
    def useFile(self, fd, showTime = 1, showThread = 0, showFile = 1):
        self.close()
        self.fd = fd
        if isinstance(fd, str):
            fd = open(fd, 'w+')
            self._close = fd.close # Only close file desc. we open
        self._out = fd.write
        self._flush = fd.flush
        self._showTime = showTime
        self._showThread = showThread
        self._showFile = showFile

    #
    # Setup to use Python syslog module.
    #
    def useSyslog(self, ident, opts, facility, showTime = 0, showThread = 0, showFile = 1):
        import syslog
        self.close()
        syslog.openlog(ident, opts, facility)
        self._out = syslog.syslog
        self._close = syslog.closelog
        self._showTime = showTime
        self._showThread = showThread
        self._showFile = showFile

    #
    # Setup to use whatever is set in sys.stderr.
    #
    def useStdErr(self, showTime = 1, showThread = 0, showFile = 1):
        self.useFile(sys.stderr, showTime, showThread, showFile)

    #
    # Setup to use whatever is set in sys.stdout.
    #
    def useStdOut(self, showTime = 1, showThread = 0, showFile = 1):
        self.useFile(sys.stdout, showTime, showThread, showFile)

    #
    # Set flag that determines if timestamp is printed in output.
    #
    def showTime(self, showTime = 1):
        self._showTime = showTime
 
    #
    # Set flag that determines if thread ID is printed in output.
    #
    def showThread(self, showThread = 1):
        self._showThread = showThread

    #
    # Set flag that determines if filename that contains the log statement is
    # printed.
    #
    def showFile(self, showFile = 1):
        self._showFile = showFile

    #
    # set flag that determines if function name is printed in output.
    #
    def showFunction(self, showFunc = 1):
        self._showFunc = showFunc
 
    #
    # Set flag that determines if the first argument (self) of a method is
    # printed in Begin() output.
    #
    def showSelf(self, showSelf = 1):
        self._showSelf = showSelf

    #
    # Internal function that builds the string that is ultimately sent to the
    # current sink device.
    #
    def _formatOutput(self, level, args, tag = ""):

        # Try to get context information. Looking for the name of the file we
        # are in, the name of the function (with possible class name
        # prepended), and if we are formatting a Begin() call, a list of
        # argnames and values that describe what is being passed into the
        # function we are logging.
        #
        doBegin = tag == self.kEntryTag and len(args) == 0
        fileName, proc, bArgs = self._procInfo(doBegin)
        if len(bArgs) > 0:
            args = bArgs
 
        # Generate timestamp
        #
        bits = []
        if self._showTime:
            bits.append(strftime("%Y%m%d.%H%M%S", gmtime()))

        #
        # Generate thread ID
        #
        if self._showThread:
            bits.append('#{} '.format(get_ident()))

        #
        # Print file name containing the log statement
        #
        if self._showFile:
            bits.append(fileName)

        #
        # Print the function name containing the log statement. May also have a
        # class name if this is a method.
        #
        if self._showFunc:
            bits.append(proc)

        #
        # Print BEG/END tag
        #
        if len(tag) > 0:
            bits.append(tag)

        #
        # Append each argument to message string
        #
        bits.extend([str(z) for z in args])
        return ' '.join(bits) + '\n'

    #
    # Return the name of the class that defines the function being logged. We
    # walk the class hierarchy just like Python does in order to locate the
    # actual defining class.
    #
    def _definingClass(self, theClass, codeObj):
        classDict = theClass.__dict__
        name = codeObj.co_name
        if name in classDict:
            tmp = classDict[name]
            if tmp.__code__ == codeObj:
                return theClass.__name__
        for eachClass in theClass.__bases__:
            name = self._definingClass(eachClass, codeObj)
            if name != None:
                return name
        return None

    #
    # Returns a tuple containing information about the function being logged:
    # file name, caller name, argument list
    #
    def _procInfo(self, genArgs = 0):
        fileName = '__main__'
        procName = '?'
        args = []

        frame = inspect.currentframe()
        frame = frame.f_back    # Get out of _procInfo
        if frame:
            frame = frame.f_back # Get out of _formatOutput
            if frame:
                frame = frame.f_back # Get ouf of _log

        if frame:

            #
            # Extract the code object that contains the call to our log method.
            #
            code = frame.f_code
            fileName = os.path.split(code.co_filename)[1]
            procName = code.co_name
            numArgs = code.co_argcount
            if numArgs > 0:
                
                #
                # Assume we will display first argument. If we determine that
                # we are logging a method, obey the setting for showSelf.
                #
                firstArg = 0
 
                #
                # Get first argument and see if it is an object (ala self)
                #
                frameLocals = frame.f_locals
                varNames = code.co_varnames
                obj = frameLocals[varNames[0]]
                if hasattr(obj, '__class__'):
                    className = None
                    for each in inspect.getmro(type(obj)):
                        if each.__dict__.get(code.co_name):
                            className = each.__name__
                            break
                    if className:
                        procName = className + '.' + procName
                        if not self._showSelf:
                            firstArg = 1
 
                #
                # Create a list of argument names and their runtime values.
                # Only done if we are in a Begin() log method.
                #
                if genArgs:
                    for each in varNames[firstArg : numArgs]:
                        value = frameLocals[each]
                        if isinstance(value, str):
                            arg = each + ': ' + value
                        else:
                            arg = each + ': ' + repr(value)
                        args.append(arg)
                    each = None

        obj = frameLocals = None
        frame = code = None
        return (fileName, procName, args)

class Foo(object):
    def __init__(self):
        gLog.begin()
        gLog.end()
        
    def bar(self):
        gLog.begin()
        gLog.end()

def test():
    def a():
        gLog.begin()
        gLog.debug('this is a test')
        gLog.end()
    a()
    f = Foo()
    f.bar()

def DelLog():
    delattr(__main__.__builtins__, 'gLog')

#
# First time we are imported, install a global variable `gLog' for everyone to
# see and use. By default, use stderr.
#
if not hasattr(__main__.__builtins__, 'gLog'):
    __main__.__builtins__.gLog = Logger()
    gLog.useStdErr()
