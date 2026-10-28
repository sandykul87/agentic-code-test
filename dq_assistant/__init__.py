"""Data Quality Assistant.

A small command-line tool that reads item master records (JSON or CSV), runs a
fixed set of checks, and writes a JSON Report of review candidates for a human
data steward. It never changes the input data.

The runtime depends on nothing but the Python 3 standard library.
"""

__version__ = "0.1.0"
