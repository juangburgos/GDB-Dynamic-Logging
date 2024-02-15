## GDB Dynamic Logging

A simple python extension to create and manage special debug breakpoints that _do not stop the application execution_, but instead, create user-defined log entries, in a user-defined log file, without having to stop or re-compile the application.

### Motivation

The goal is to add log entries in points of interest of an application, in cases where stopping the application is not acceptable. One specific use case is to understand bugs that only occur _in deployment_. Normally, this entails stopping the application, add _intrumentation_ to such points, re-compile, re-deploy and re-run. This makes the debugging cycle slow, painful and inconvienient.

Ideally, one would want to attach a debug session to the running application, and add such points without interfeering with the application. Additionally, the ability to print the contents of variables, call stack, etc, is desirable. GDB added support for similar functionality with [_GDB Tracepoints_](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Tracepoints.html), but sadly they seem [currently broken and largely unmaintained](https://stackoverflow.com/questions/77075577/gdb-tracing-target-returns-error-code-01-after-continue-command).

Luckly GDB offers a python integration [with an API](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Python-API.html) that allows, along other things, to create [custom breakpoints](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Breakpoints-In-Python.html#Breakpoints-In-Python), with user-defined behaviour. This extension leverages the python API to achieve these goals.

### Requirements

* A GDB version supporting the Python API.

* A GDB session with _debug symbols_ loaded for the application.

### Workflow

* Attach GDB to a running application [without stopping it](https://stackoverflow.com/questions/9746018/gdb-attach-to-a-process-without-stop).

* Load debug symbols (if not already present in the application itself).

* Source (load) the python extension `dlog.py`).

* Define a target log file (`logfile` command).

* Add log entries manually (`addlog` command), or _import_ an existing "log definitions" file (`importlogs` command, ["breakpoint definitions"](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Save-Breakpoints.html) files are also supported).

* Profit.

Note that if log definitions are created directly in deployment, some error in defining the log entry might affect the application flow, therefore it is recommended to create a "log definitions" file in a local debug session first, and then load it in deployment. The `testlog` command can be used, once stopped in a breakpoint, to test how a log entry would be printed in the target log file.

## The Python Extenstion

After sourcing (loading) the `dlog.py` script, the following user defined commands are available in GDB:

* `logfile` : without argument, prints the currently defined log file, `stdout` by default. Argument can be a file path or `none` to disable.

* `getthreadname` : prints the sanitized (no newlines or quotes) thread name, or of non is set (with `pthread_setname_np`), then the corresponding thread id. No arguments.

* `getlocspec` : prints the sanitized (just base name) source file and line of the current frame. No arguments.

* `getsimplebt` : prints the sanitized (as in `getlocspec`) current *backtrace*. No arguments.

* `getformattime` : print the current timestamp using a custom format as defined by the `strftime` routine. Argument is the desired format.

* `subprocexec` : execute a shell command and print the sanitized output (note GDB's `shell` command's output cannot be captured through python).

* `addlog` : adds an instance of the python script's `class Log` which implements a GDB breakpoint that does not stop when hit, but prints a used-defined log line into the file defined by `logfile`. The syntax for logs _locations_, is the same as for [setting normal breakpoints](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Set-Breaks.html).

The `addlog` command syntax is:

```
addlog [location] "[message template with placeholders]" "[gdb expression]" "[gdb expression]" ... "[gdb expression]"`
```

The _placeholders_ in the _message template_ are defined with curly braces (`{}`). The number of placeholders in the messegae template must match the number of _gdb expression_ added after. For example:

```bash
# Note there are 5 instances of {} (placeholders) and 5 subsequent gdb expressions
addlog main.cpp:5 "{} {} INFO Executing foo(); a={}, b={} [{}]" "getformattime %d/%m/%Y-%H:%M:%S.%f" "getthreadname" "printf \"%i\", a" "printf \"%i\", b" "getlocspec"
```

The _gdb expression_ must be an expression that actually prints some information, e.g. [print the contents of a variable](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Data.html) `printf "%i", b`. Note in the example above, the quotes have to be _escaped_.

* `testlog` : print the used-defined log line at the current frame while stopped in an interactive debug session, useful to test what the output of the used-defined log would look like when using `addlog`.

A more complete example:

```bash
# ... in an attached GDB session with debug symbols

# import the python extension
source ./../trace_test/dlog.py
# define target log file
logfile ./test.log
# add log definitions (manually)
addlog main.cpp:5 "{} {} INFO Executing foo(); a={}, b={} [{}]" "getformattime %d/%m/%Y-%H:%M:%S.%f" "getthreadname" "printf \"%i\", a" "printf \"%i\", b" "getlocspec"
addlog main.cpp:11 "{} {} INFO After foo(); n={} [{}]" "getformattime %d/%m/%Y-%H:%M:%S.%f" "getthreadname" "printf \"%i\", n" "getlocspec"
# once stopped in a point of interest, interactivelly test a log definition at that point
testlog "{} {} INFO locals: {} [{}]" "getformattime %d/%m/%Y-%H:%M:%S.%f" "getthreadname" "info locals" "getlocspec"
```

* `listlogs` : prints the list of logs that have been added using `addlog` with their respective log number which can be used to remove an specific log using `rmlog`.

* `rmlog` : removes the log instance associated with the log number passed as an argument, if no argument is passed, all logs are removed.

* `exportlogs` : exports the log definitions to the file passed as argument, such file can later be used to load the log definitions using `importlogs` or by simply sourcing the file.

* `importlogs` : imports log definitions from a file passed as argument, created by the `exportlogs`, if more arguments are passed, it is assumed to be a file containing breakpoint definitions (`save breakpoints`), whose locations are used to generate logs using the extra arguments as the rest of the log definition.

```bash
listlogs
#Num   Location   Message
#0      main.cpp:5    {} {} INFO locals: {} [{}]
#1      main.cpp:11    {} {} INFO locals: {} [{}]
#2      main.cpp:12    hello

rmlog 1

listlogs
#Num   Location   Message
#0      main.cpp:5    {} {} INFO locals: {} [{}]
#2      main.cpp:12    hello

# import from breakpoint definition file
importlogs ./bp.txt "{} {} INFO locals: {} [{}]" "getformattime %d/%m/%Y-%H:%M:%S.%f" "getthreadname" "info locals" "getlocspec"

exportlogs ./tc.txt
# import from log definition file
importlogs ./tc.txt
```