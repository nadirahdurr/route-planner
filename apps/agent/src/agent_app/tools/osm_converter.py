"""Convert OSM PBF files to required terrain data format."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any

try:
    import osmium
    from shapely.geometry import mapping, LineString
    OSMIUM_AVAILABLE = True
except ImportError:
    OSMIUM_AVAILABLE = False


class RoadHandler(osmium.SimpleHandler):
    """Extract roads from OSM data."""
    
    def __init__(self):
        super().__init__()
        self.roads = []
    
    def way(self, w):
        """Process ways (roads)."""
        if 'highway' in w.tags:
            try:
                coords = [(node.lon, node.lat) for node in w.nodes]
                if len(coords) >= 2:
                    self.roads.append({
                        "type": "Feature",
                        "geometry": mapping(LineString(coords)),
                        "properties": {
                            "id": w.id,
                            "highway": w.tags.get('highway', ''),
                            "name": w.tags.get('name', '')
                        }
                    })
            except osmium.InvalidLocationError:
                pass  # Skip ways with invalid coordinates


class ObstacleHandler(osmium.SimpleHandler):
    """Extract obstacles (buildings, water) from OSM data."""
    
    def __init__(self):
        super().__init__()
        self.obstacles = []
    
    def area(self, a):
        """Process areas (buildings, water bodies)."""
        is_building = 'building' in a.tags
        is_water = a.tags.get('natural') == 'water' or a.tags.get('water') is not None
        is_military = a.tags.get('landuse') == 'military'
        
        if is_building or is_water or is_military:
            try:
                outer_coords = []
                for ring in a.outer_rings():
                    coords = [(node.lon, node.lat) for node in ring]
                    if len(coords) >= 3:
                        outer_coords.append(coords)
                
                if outer_coords:
                    from shapely.geometry import Polygon
                    self.obstacles.append({
                        "type": "Feature",
                        "geometry": mapping(Polygon(outer_coords[0])),
                        "properties": {
                            "id": a.id,
                            "type": "building" if is_building else ("water" if is_water else "military")
                        }
                    })
            except (osmium.InvalidLocationError, ValueError):
                pass  # Skip invalid geometries


class OSMConverter:
    """Convert OSM PBF files to GeoJSON format for terrain bundles."""

    @staticmethod
    def is_osm_pbf(file_path: Path) -> bool:
        """Check if a file is an OSM PBF file."""
        return file_path.suffix.lower() in ['.pbf', '.osm.pbf'] or 'osm.pbf' in file_path.name.lower()

    @staticmethod
    def convert_to_roads(osm_pbf_path: Path, output_path: Path) -> None:
        """
        Convert OSM PBF file to roads GeoJSON using pyosmium.
        
        Args:
            osm_pbf_path: Path to the OSM PBF file
            output_path: Path where the roads.geojson will be saved
        """
        if not OSMIUM_AVAILABLE:
            raise RuntimeError(
                "osmium is not installed. Install dependencies with: pip install osmium shapely"
            )
        
        import logging
        logger = logging.getLogger("uvicorn")
        
        logger.info(f"🛣️  Converting roads from {osm_pbf_path.name}...")
        handler = RoadHandler()
        handler.apply_file(str(osm_pbf_path), locations=True)
        logger.info(f"   Found {len(handler.roads)} road features")
        
        geojson = {
            "type": "FeatureCollection",
            "features": handler.roads
        }
        
        with open(output_path, 'w') as f:
            json.dump(geojson, f, indent=2)
        logger.info(f"✅ Saved roads to {output_path.name}")

    @staticmethod
    def convert_to_obstacles(osm_pbf_path: Path, output_path: Path) -> None:
        """
        Convert OSM PBF file to obstacles GeoJSON using pyosmium.
        
        Args:
            osm_pbf_path: Path to the OSM PBF file
            output_path: Path where the obstacles.geojson will be saved
        """
        if not OSMIUM_AVAILABLE:
            OSMConverter._create_empty_geojson(output_path)
            return
        
        import logging
        logger = logging.getLogger("uvicorn")
        
        try:
            logger.info(f"🏗️  Converting obstacles from {osm_pbf_path.name}...")
            handler = ObstacleHandler()
            handler.apply_file(str(osm_pbf_path), locations=True)
            logger.info(f"   Found {len(handler.obstacles)} obstacle features")
            
            geojson = {
                "type": "FeatureCollection",
                "features": handler.obstacles
            }
            
            with open(output_path, 'w') as f:
                json.dump(geojson, f, indent=2)
            logger.info(f"✅ Saved obstacles to {output_path.name}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to extract obstacles: {e}, creating empty file")
            # If extraction fails, create empty file
            OSMConverter._create_empty_geojson(output_path)

    @staticmethod
    def _create_empty_geojson(output_path: Path) -> None:
        """Create an empty GeoJSON FeatureCollection."""
        geojson = {
            "type": "FeatureCollection",
            "features": []
        }
        with open(output_path, 'w') as f:
            json.dump(geojson, f)

    @staticmethod
    def create_placeholder_dem(output_path: Path, bounds: dict = None) -> None:
        """
        Create a placeholder DEM file with proper schema.
        
        Args:
            output_path: Path where dem.json will be saved
            bounds: Optional bounds dict with minx, miny, maxx, maxy
        """
        from datetime import datetime, timezone
        
        if bounds is None:
            bounds = {
                "minx": -117.0,
                "miny": 34.0,
                "maxx": -116.99,
                "maxy": 34.01
            }
        
        # Create a simple 10x10 grid with flat elevation (100m)
        grid = [[100] * 10 for _ in range(10)]
        
        dem_data = {
            "metadata": {
                "origin": {
                    "lat": bounds.get("miny", 34.0),
                    "lon": bounds.get("minx", -117.0)
                },
                "cell_size_m": 100,
                "ttl_hours": 720,
                "last_updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            },
            "grid": grid
        }
        
        with open(output_path, 'w') as f:
            json.dump(dem_data, f, indent=2)

    @staticmethod
    def create_placeholder_landcover(output_path: Path, bounds: dict = None) -> None:
        """
        Create a placeholder land cover file with proper schema.
        
        Args:
            output_path: Path where landcover.json will be saved
            bounds: Optional bounds dict with minx, miny, maxx, maxy
        """
        from datetime import datetime, timezone
        
        if bounds is None:
            bounds = {
                "minx": -117.0,
                "miny": 34.0,
                "maxx": -116.99,
                "maxy": 34.01
            }
        
        # Create a simple 10x10 grid with "open" terrain (most neutral)
        grid = [["open"] * 10 for _ in range(10)]
        
        landcover_data = {
            "metadata": {
                "origin": {
                    "lat": bounds.get("miny", 34.0),
                    "lon": bounds.get("minx", -117.0)
                },
                "cell_size_m": 100,
                "ttl_hours": 720,
                "last_updated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            },
            "classes": {
                "trail": {
                    "cost_factor": 0.8,
                    "exposure": 0.2,
                    "speed_modifier": 1.1
                },
                "forest": {
                    "cost_factor": 1.2,
                    "exposure": 0.4,
                    "speed_modifier": 0.85
                },
                "open": {
                    "cost_factor": 1.0,
                    "exposure": 0.6,
                    "speed_modifier": 1.0
                },
                "wetland": {
                    "cost_factor": 1.5,
                    "exposure": 0.5,
                    "speed_modifier": 0.7
                },
                "road": {
                    "cost_factor": 0.7,
                    "exposure": 0.3,
                    "speed_modifier": 1.2
                }
            },
            "grid": grid
        }
        
        with open(output_path, 'w') as f:
            json.dump(landcover_data, f, indent=2)
