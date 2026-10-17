# SPDX-License-Identifier: MIT
"""Old deployment scripts cannot silently operate on a production home."""
def retired():
    raise SystemExit("This deployment helper has been replaced by agent-qqbot install/configure/start. Use the unified launcher with a separate native instance home; no legacy data or root service is changed automatically.")
