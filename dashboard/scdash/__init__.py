"""scdash: the side-screen dashboard for Star Citizen (stage 1: log reading, events, state).

This package sits beside the entry script `dashboard/scdash.py`. With `dashboard/` on sys.path,
`import scdash` resolves to this package, not to that script, because the import system prefers
a package directory over a module file of the same name. That only holds while this `__init__.py`
exists: a folder without one would be a namespace package, and the script would win.
"""

__version__ = "0.1.0"
