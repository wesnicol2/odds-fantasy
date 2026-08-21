"""Shared test bootstrap.

pytest imports conftest.py before collecting any test module, so putting the
sys.path setup here lets every test file import `refactored` normally no matter
which working directory the suite is invoked from. This used to be a four-line
block copied into the top of all six test modules.
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
