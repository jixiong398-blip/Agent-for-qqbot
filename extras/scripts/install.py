"""Compatibility dispatcher for the unified native installer."""
import sys
from bootstrap import main
if __name__ == "__main__":
    sys.argv[1:] = ["install", *sys.argv[1:]]
    raise SystemExit(main())
