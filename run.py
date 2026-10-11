#!/usr/bin/env python3
"""Local development server."""

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3847"))
    app.run(host="0.0.0.0", port=port, debug=True)
