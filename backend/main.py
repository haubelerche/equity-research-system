from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("backend.api:app", host="0.0.0.0", port=8010, reload=False)


if __name__ == "__main__":
    main()

