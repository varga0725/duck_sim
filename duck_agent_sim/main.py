import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from duck_agent_sim.bridge.api import router as api_router
from duck_agent_sim.bridge.websocket import router as ws_router
from duck_agent_sim.config import DUCK_SIM_MODE, BRIDGE_PORT, BRIDGE_HOST

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("duck-agent-sim")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Sequence
    logger.info("=========================================")
    logger.info("  Open Duck Agent Simulation Bridge API  ")
    logger.info("=========================================")
    logger.info(f"Sim Mode:    {DUCK_SIM_MODE.upper()}")
    logger.info(f"Listen Host: {BRIDGE_HOST}")
    logger.info(f"Listen Port: {BRIDGE_PORT}")
    logger.info("=========================================")
    
    from duck_agent_sim.services import app_context
    logger.info("Eagerly initializing AppContext and active simulator services...")
    app_context.start()
    
    yield
    # Shutdown Sequence
    logger.info("Stopping Duck Agent Simulation Bridge API...")
    from duck_agent_sim.services import app_context
    app_context.shutdown()

# Initialize FastAPI
app = FastAPI(
    title="Duck Agent Simulation MVP",
    description="High-level API Bridge connecting AI Agents to the simulated Open Duck Mini v2 robot in MuJoCo",
    version="0.1.0",
    lifespan=lifespan
)

# Enable CORS for easy Dashboard integration in later phases
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Wire up routers
app.include_router(api_router, tags=["REST Control API"])
app.include_router(ws_router, tags=["WebSocket Telemetry Stream"])
