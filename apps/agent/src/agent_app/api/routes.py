from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import StreamingResponse
import json

from agent_app.config import Settings, get_settings
from agent_app.graph import RoutePlannerGraph
from agent_app.models import PlanCreateRequest, PlanResult, PlanRunStatus, TerrainBundleCreate, TerrainBundleSummary

router = APIRouter(prefix="/api/v1", tags=["planner"])

# Store upload progress
upload_progress: Dict[str, dict] = {}


def get_graph() -> RoutePlannerGraph:
    return RoutePlannerGraph()


def get_settings_dep() -> Settings:
    return get_settings()


@router.get("/terrain", response_model=List[TerrainBundleSummary])
def list_terrain_bundles(
    graph: RoutePlannerGraph = Depends(get_graph),
) -> List[TerrainBundleSummary]:
    """List all available terrain bundles."""
    bundles = graph.terrain_tool.list_bundles()
    return [TerrainBundleSummary(**bundle) for bundle in bundles]


def process_terrain_background(upload_id: str, name: str, file_path, description: str = None):
    """Background task to process terrain bundle."""
    logger = logging.getLogger("uvicorn")
    
    try:
        import os
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        
        # Check if OSM PBF file
        from agent_app.tools.osm_converter import OSMConverter
        is_osm = OSMConverter.is_osm_pbf(file_path)
        
        if is_osm:
            # Warn about large files
            if file_size_mb > 1000:  # > 1GB
                upload_progress[upload_id] = {
                    "status": "processing", 
                    "message": f"Processing large OSM file ({file_size_mb:.1f} MB). This may take 10-20 minutes...", 
                    "progress": 15
                }
                logger.warning(f"⚠️  Large OSM file detected: {file_size_mb:.1f} MB - processing may take a long time")
            else:
                upload_progress[upload_id] = {"status": "processing", "message": "Detected OSM PBF file, preparing conversion...", "progress": 15}
        else:
            upload_progress[upload_id] = {"status": "processing", "message": "Extracting archive...", "progress": 15}
        
        upload_progress[upload_id] = {"status": "processing", "message": "Converting roads from OSM data...", "progress": 20}
        
        graph = RoutePlannerGraph()
        
        upload_progress[upload_id] = {"status": "processing", "message": "Extracting obstacles (buildings, water, etc)...", "progress": 60}
        
        bundle = graph.terrain_tool.register(
            name,
            archive_path=file_path,
            auto_activate=True,
        )
        
        upload_progress[upload_id] = {
            "status": "completed",
            "message": "Terrain bundle ready! Refresh to see it in the dropdown.",
            "progress": 100,
            "bundle": {
                "id": bundle.terrain_id,
                "name": name,
                "description": description,
            }
        }
        logger.info(f"✅ Terrain bundle registered: {bundle.terrain_id}")
    except Exception as e:
        logger.error(f"❌ Failed to process terrain: {str(e)}")
        upload_progress[upload_id] = {
            "status": "error",
            "message": f"Failed: {str(e)}. Try a smaller region (state-level instead of multi-state).",
            "progress": 0
        }


@router.post("/terrain/upload")
async def upload_terrain(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    description: str = Form(None),
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings_dep),
):
    """Upload a terrain bundle archive (processes in background)."""
    logger = logging.getLogger("uvicorn")
    
    upload_id = f"{name.replace(' ', '_')}_{int(datetime.now().timestamp())}"
    logger.info(f"📤 Upload started: {file.filename} (name: {name}, id: {upload_id})")
    
    # Save the uploaded file
    upload_path = settings.data_root / "uploads"
    upload_path.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_path / file.filename
    logger.info(f"💾 Saving to: {file_path}")
    
    upload_progress[upload_id] = {"status": "uploading", "message": "Saving file...", "progress": 5}
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    logger.info(f"✅ File saved: {file_size_mb:.2f} MB")
    
    upload_progress[upload_id] = {"status": "uploaded", "message": f"File saved ({file_size_mb:.1f} MB)", "progress": 8}
    
    # Process in background
    background_tasks.add_task(process_terrain_background, upload_id, name, file_path, description)
    
    return {"upload_id": upload_id, "message": "Upload received, processing in background"}


@router.get("/terrain/upload/{upload_id}/status")
async def get_upload_status(upload_id: str):
    """Get status of a terrain upload."""
    if upload_id not in upload_progress:
        raise HTTPException(status_code=404, detail="Upload not found")
    return upload_progress[upload_id]


@router.get("/terrain/upload/{upload_id}/progress")
async def stream_upload_progress(upload_id: str):
    """Stream real-time progress updates via SSE."""
    async def event_generator():
        while True:
            if upload_id in upload_progress:
                progress = upload_progress[upload_id]
                yield f"data: {json.dumps(progress)}\n\n"
                
                if progress["status"] in ["completed", "error"]:
                    break
            
            await asyncio.sleep(0.5)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/terrain", response_model=PlanRunStatus)
def register_terrain(
    request: TerrainBundleCreate,
    settings: Settings = Depends(get_settings_dep),
) -> PlanRunStatus:
    # TODO: wire into LocalTerrainTool.register and persist metadata
    graph = RoutePlannerGraph()
    bundle = graph.terrain_tool.register(
        request.name,
        archive_path=request.bundle_path,
        auto_activate=request.auto_activate,
    )
    now = datetime.now(timezone.utc)
    return PlanRunStatus(
        run_id=bundle.terrain_id,
        status="completed",
        created_at=now,
        updated_at=now,
        message="Terrain bundle registration stub",
    )


@router.post("/plans", response_model=PlanResult)
def create_plan(
    request: PlanCreateRequest,
    graph: RoutePlannerGraph = Depends(get_graph),
) -> PlanResult:
    try:
        result = graph.run(
            terrain_id=request.terrain_id,
            start_lat=request.start_lat,
            start_lon=request.start_lon,
            end_lat=request.end_lat,
            end_lon=request.end_lon,
            preference=request.preference,
            policy=request.policy,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return PlanResult(
        run_id="demo-run",
        approved_route_id=None,
        artifact_base=None,
        export_paths=[],
        llm_brief=result.get("llm_decision"),
        route_payload=result.get("route_response"),
    )
