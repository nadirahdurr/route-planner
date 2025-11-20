#!/usr/bin/env python3
"""
Convert standard geospatial data formats into route planner terrain bundle format.

Requirements:
    pip install rasterio geopandas shapely numpy

Usage:
    python convert_terrain_data.py --dem <dem.tif> --landcover <landcover.tif> --roads <roads.shp> --output <bundle_name>
"""

import argparse
import json
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from shapely.geometry import mapping


def convert_dem_to_json(dem_path: Path, output_path: Path, bounds=None):
    """Convert DEM GeoTIFF to JSON format."""
    print(f"Converting DEM: {dem_path}")
    
    with rasterio.open(dem_path) as src:
        # Read the DEM data
        dem_data = src.read(1)
        transform = src.transform
        
        # Get bounds
        if bounds is None:
            bounds = src.bounds
        
        # Create grid of coordinates
        height, width = dem_data.shape
        xs = np.linspace(bounds.left, bounds.right, width)
        ys = np.linspace(bounds.top, bounds.bottom, height)
        
        # Sample data (reduce resolution if too large)
        sample_factor = max(1, width // 100)
        dem_sampled = dem_data[::sample_factor, ::sample_factor]
        xs_sampled = xs[::sample_factor]
        ys_sampled = ys[::sample_factor]
        
        # Create output structure
        dem_json = {
            "type": "DEM",
            "crs": "EPSG:4326",
            "bounds": {
                "minx": bounds.left,
                "miny": bounds.bottom,
                "maxx": bounds.right,
                "maxy": bounds.top
            },
            "resolution": {
                "x": (bounds.right - bounds.left) / width,
                "y": (bounds.top - bounds.bottom) / height
            },
            "data": []
        }
        
        # Add elevation points
        for i, y in enumerate(ys_sampled):
            for j, x in enumerate(xs_sampled):
                elevation = float(dem_sampled[i, j])
                if not np.isnan(elevation):
                    dem_json["data"].append({
                        "lat": float(y),
                        "lon": float(x),
                        "elevation": elevation
                    })
        
        print(f"  Processed {len(dem_json['data'])} elevation points")
        
        with open(output_path, 'w') as f:
            json.dump(dem_json, f, indent=2)
        
        print(f"  Saved to: {output_path}")


def convert_landcover_to_json(landcover_path: Path, output_path: Path, bounds=None):
    """Convert land cover GeoTIFF to JSON format."""
    print(f"Converting Land Cover: {landcover_path}")
    
    with rasterio.open(landcover_path) as src:
        landcover_data = src.read(1)
        
        if bounds is None:
            bounds = src.bounds
        
        height, width = landcover_data.shape
        xs = np.linspace(bounds.left, bounds.right, width)
        ys = np.linspace(bounds.top, bounds.bottom, height)
        
        # Sample data
        sample_factor = max(1, width // 100)
        lc_sampled = landcover_data[::sample_factor, ::sample_factor]
        xs_sampled = xs[::sample_factor]
        ys_sampled = ys[::sample_factor]
        
        landcover_json = {
            "type": "LandCover",
            "crs": "EPSG:4326",
            "bounds": {
                "minx": bounds.left,
                "miny": bounds.bottom,
                "maxx": bounds.right,
                "maxy": bounds.top
            },
            "data": []
        }
        
        # Add land cover points
        for i, y in enumerate(ys_sampled):
            for j, x in enumerate(xs_sampled):
                lc_value = int(lc_sampled[i, j])
                if lc_value > 0:
                    landcover_json["data"].append({
                        "lat": float(y),
                        "lon": float(x),
                        "class": lc_value,
                        "type": get_landcover_type(lc_value)
                    })
        
        print(f"  Processed {len(landcover_json['data'])} land cover points")
        
        with open(output_path, 'w') as f:
            json.dump(landcover_json, f, indent=2)
        
        print(f"  Saved to: {output_path}")


def get_landcover_type(value: int) -> str:
    """Map NLCD codes to simplified land cover types."""
    landcover_map = {
        11: "water",
        21: "developed",
        22: "developed",
        23: "developed",
        24: "developed",
        31: "barren",
        41: "forest",
        42: "forest",
        43: "forest",
        52: "shrub",
        71: "grassland",
        81: "pasture",
        82: "crops",
        90: "wetlands",
        95: "wetlands",
    }
    return landcover_map.get(value, "unknown")


def convert_roads_to_geojson(roads_path: Path, output_path: Path, bounds=None):
    """Convert roads shapefile or GeoJSON to standardized GeoJSON."""
    print(f"Converting Roads: {roads_path}")
    
    # Read file (geopandas handles both shapefiles and GeoJSON)
    gdf = gpd.read_file(roads_path)
    
    # Ensure CRS is WGS84
    if gdf.crs != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")
    
    # Filter by bounds if provided
    if bounds:
        gdf = gdf.cx[bounds.left:bounds.right, bounds.bottom:bounds.top]
    
    # Simplify geometries to reduce file size
    gdf.geometry = gdf.geometry.simplify(0.0001)
    
    # Convert to GeoJSON structure
    features = []
    for idx, row in gdf.iterrows():
        if row.geometry.geom_type in ['LineString', 'MultiLineString']:
            features.append({
                "type": "Feature",
                "geometry": mapping(row.geometry),
                "properties": {
                    "id": idx,
                    "type": "road"
                }
            })
    
    geojson = {
        "type": "FeatureCollection",
        "features": features
    }
    
    print(f"  Processed {len(features)} road features")
    
    with open(output_path, 'w') as f:
        json.dump(geojson, f, indent=2)
    
    print(f"  Saved to: {output_path}")


def create_empty_obstacles(output_path: Path):
    """Create an empty obstacles GeoJSON file."""
    print("Creating empty obstacles file")
    
    geojson = {
        "type": "FeatureCollection",
        "features": []
    }
    
    with open(output_path, 'w') as f:
        json.dump(geojson, f, indent=2)
    
    print(f"  Saved to: {output_path}")


def create_terrain_bundle(dem_path, landcover_path, roads_path, output_name, obstacles_path=None):
    """Create a complete terrain bundle."""
    print(f"\n{'='*60}")
    print(f"Creating terrain bundle: {output_name}")
    print(f"{'='*60}\n")
    
    # Create temporary directory for converted files
    temp_dir = Path("temp_terrain")
    temp_dir.mkdir(exist_ok=True)
    
    # Convert each file
    dem_json = temp_dir / "dem.json"
    landcover_json = temp_dir / "landcover.json"
    roads_geojson = temp_dir / "roads.geojson"
    obstacles_geojson = temp_dir / "obstacles.geojson"
    
    try:
        convert_dem_to_json(Path(dem_path), dem_json)
        convert_landcover_to_json(Path(landcover_path), landcover_json)
        convert_roads_to_geojson(Path(roads_path), roads_geojson)
        
        if obstacles_path:
            # TODO: implement obstacles conversion
            create_empty_obstacles(obstacles_geojson)
        else:
            create_empty_obstacles(obstacles_geojson)
        
        # Create zip archive
        zip_path = Path(f"{output_name}.zip")
        print(f"\nCreating archive: {zip_path}")
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(dem_json, "dem.json")
            zipf.write(landcover_json, "landcover.json")
            zipf.write(roads_geojson, "roads.geojson")
            zipf.write(obstacles_geojson, "obstacles.geojson")
        
        print(f"\n{'='*60}")
        print(f"✅ Terrain bundle created successfully!")
        print(f"📦 File: {zip_path.absolute()}")
        print(f"{'='*60}\n")
        print("You can now upload this file to the Mission Route Planner.")
        
    finally:
        # Cleanup temp files
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


def main():
    parser = argparse.ArgumentParser(
        description="Convert geospatial data to route planner terrain bundle format"
    )
    parser.add_argument("--dem", required=True, help="Path to DEM GeoTIFF file")
    parser.add_argument("--landcover", required=True, help="Path to land cover GeoTIFF file")
    parser.add_argument("--roads", required=True, help="Path to roads file (shapefile or GeoJSON)")
    parser.add_argument("--obstacles", help="Path to obstacles file (shapefile or GeoJSON, optional)")
    parser.add_argument("--output", required=True, help="Output bundle name (without extension)")
    
    args = parser.parse_args()
    
    create_terrain_bundle(
        dem_path=args.dem,
        landcover_path=args.landcover,
        roads_path=args.roads,
        output_name=args.output,
        obstacles_path=args.obstacles
    )


if __name__ == "__main__":
    main()
