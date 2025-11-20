from __future__ import annotations

import shutil
import tarfile
import zipfile
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from agent_app.config import get_settings
from agent_app.tools.osm_converter import OSMConverter


class TerrainContext(BaseModel):
    terrain_id: str
    dem_path: Path
    landcover_path: Path
    roads_path: Path
    obstacles_path: Path


class LocalTerrainTool:
    """Loads and validates terrain bundles stored on disk."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def load(self, terrain_id: str) -> TerrainContext:
        bundle_dir = self.settings.data_root / terrain_id
        if not bundle_dir.exists():
            raise FileNotFoundError(f"Terrain bundle '{terrain_id}' not found at {bundle_dir}")

        dem = bundle_dir / "dem.json"
        landcover = bundle_dir / "landcover.json"
        roads = bundle_dir / "roads.geojson"
        obstacles = bundle_dir / "obstacles.geojson"

        for path in (dem, landcover, roads, obstacles):
            if not path.exists():
                raise FileNotFoundError(f"Terrain bundle missing required file: {path}")

        return TerrainContext(
            terrain_id=terrain_id,
            dem_path=dem,
            landcover_path=landcover,
            roads_path=roads,
            obstacles_path=obstacles,
        )

    def register(self, name: str, archive_path: Path, *, auto_activate: bool = True) -> TerrainContext:
        """Extract terrain bundle archive and validate contents."""
        import logging
        logger = logging.getLogger("uvicorn")
        
        target_dir = self.settings.data_root / name
        target_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Target directory: {target_dir}")
        
        # Extract archive based on file type
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive file not found: {archive_path}")
        
        try:
            # Check if it's an OSM PBF file
            if OSMConverter.is_osm_pbf(archive_path):
                logger.info(f"🗺️  Detected OSM PBF file, converting...")
                self._process_osm_pbf(archive_path, target_dir)
            elif archive_path.suffix == '.zip':
                logger.info(f"📦 Extracting ZIP archive...")
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(target_dir)
                logger.info(f"✅ ZIP extracted")
            elif archive_path.suffix in ['.tar', '.gz', '.tgz']:
                logger.info(f"📦 Extracting TAR archive...")
                with tarfile.open(archive_path, 'r:*') as tar_ref:
                    tar_ref.extractall(target_dir)
                logger.info(f"✅ TAR extracted")
            else:
                raise ValueError(f"Unsupported archive format: {archive_path.suffix}")
        except Exception as e:
            logger.error(f"❌ Extraction failed: {e}")
            # Clean up on failure
            if target_dir.exists():
                shutil.rmtree(target_dir)
            raise RuntimeError(f"Failed to extract archive: {e}") from e
        
        # Validate required files exist
        dem = target_dir / "dem.json"
        landcover = target_dir / "landcover.json"
        roads = target_dir / "roads.geojson"
        obstacles = target_dir / "obstacles.geojson"
        
        missing_files = []
        for path in (dem, landcover, roads, obstacles):
            if not path.exists():
                missing_files.append(path.name)
        
        if missing_files:
            # Clean up incomplete bundle
            shutil.rmtree(target_dir)
            raise ValueError(f"Archive is missing required files: {', '.join(missing_files)}")
        
        return TerrainContext(
            terrain_id=name,
            dem_path=dem,
            landcover_path=landcover,
            roads_path=roads,
            obstacles_path=obstacles,
        )

    def list_bundles(self) -> list[dict[str, str]]:
        """List all available terrain bundles."""
        bundles = []
        if not self.settings.data_root.exists():
            return bundles
        
        for bundle_dir in self.settings.data_root.iterdir():
            if bundle_dir.is_dir():
                # Check if it has the required files
                required_files = ["dem.json", "landcover.json", "roads.geojson", "obstacles.geojson"]
                if all((bundle_dir / f).exists() for f in required_files):
                    bundles.append({
                        "id": bundle_dir.name,
                        "name": bundle_dir.name.replace("_", " ").title(),
                        "description": f"Terrain bundle: {bundle_dir.name}"
                    })
        
        return bundles

    def _process_osm_pbf(self, osm_pbf_path: Path, target_dir: Path) -> None:
        """
        Process an OSM PBF file into terrain bundle format.
        
        Args:
            osm_pbf_path: Path to the OSM PBF file
            target_dir: Directory to store the converted files
        """
        roads_path = target_dir / "roads.geojson"
        obstacles_path = target_dir / "obstacles.geojson"
        dem_path = target_dir / "dem.json"
        landcover_path = target_dir / "landcover.json"
        
        # Convert roads from OSM
        OSMConverter.convert_to_roads(osm_pbf_path, roads_path)
        
        # Convert obstacles from OSM (or create empty)
        OSMConverter.convert_to_obstacles(osm_pbf_path, obstacles_path)
        
        # Create placeholder DEM and land cover
        # Users will need to upload these separately or we can add them later
        OSMConverter.create_placeholder_dem(dem_path)
        OSMConverter.create_placeholder_landcover(landcover_path)
