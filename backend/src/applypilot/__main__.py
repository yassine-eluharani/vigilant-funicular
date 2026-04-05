"""Enable `python -m applypilot` to start the API server."""

import uvicorn

uvicorn.run("applypilot.web.server:app", host="0.0.0.0", port=8000, reload=False)
