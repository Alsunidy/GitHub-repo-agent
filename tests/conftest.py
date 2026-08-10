import os
import sys

# Same pattern as scripts/*.py: make `import backend...` work regardless of
# the directory pytest is invoked from.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
