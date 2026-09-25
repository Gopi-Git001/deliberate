"""python -m manager_agent.ui — serve the API + built frontend on UI_HOST:UI_PORT."""

import uvicorn

from manager_agent.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("manager_agent.ui.app:app", host=settings.ui_host, port=settings.ui_port)
