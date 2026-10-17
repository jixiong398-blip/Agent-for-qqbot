"""Rebuild selected native source; never copy code over a user's legacy home."""
import sys
from bootstrap import main
if __name__ == "__main__":
    sys.argv[1:] = ["update", *sys.argv[1:]]
    raise SystemExit(main())
