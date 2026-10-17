"""Compatibility dispatcher for explicit private native configuration."""
import sys
from bootstrap import main
if __name__ == "__main__":
    sys.argv[1:] = ["configure", *sys.argv[1:]]
    raise SystemExit(main())
