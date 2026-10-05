import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("server.main:app", host="0.0.0.0", port=port, log_level="warning")
