from __future__ import annotations

import os

from backend.api import app


def main() -> None:
    import uvicorn

    uvicorn.run("backend.api:app", host="0.0.0.0", port=int(os.getenv("PORT", "8010")), reload=False)


if __name__ == "__main__":
    main()

