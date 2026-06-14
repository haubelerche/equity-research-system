from __future__ import annotations

from backend.api import app


def main() -> None:
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8010, reload=False)


if __name__ == "__main__":
    main()
