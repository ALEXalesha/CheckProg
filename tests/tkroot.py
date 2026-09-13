"""One Tk interpreter for the whole test run.

Creating and destroying tk.Tk() over and over in one process on Windows
eventually fails with 'invalid command name "tcl_findLibrary"', which the test
classes reported as "no display" and skipped. Test windows are Toplevels of
this shared, withdrawn root instead.
"""
import tkinter as tk

_root = None


def shared_root():
    global _root
    if _root is None:
        _root = tk.Tk()  # TclError propagates: callers turn it into SkipTest
        _root.withdraw()
    return _root
