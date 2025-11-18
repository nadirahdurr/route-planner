# Route Planner MCP

Offline mission route planning service, this application exposes MCP-style tools, resources, and prompt metadata so agents can plan, score, and export mission routes without network access.

## Features

- Generates 1–3 candidate routes between two coordinates using local DEM, landcover, road, and obstacle fixtures.
- Scores each route for slope, exposure, and hydrology factors.
- Provides transparent risk weights/components so commanders can recompute aggregates.
- Reports terrain coverage, hydrology checks, and per-route uncertainty for auditability.
- Includes policy metadata (composite scoring + tie-breakers) and trail coverage summaries for selection audits.
- Estimates travel time with Naismith-based pacing that adapts for load and movement mode (foot/wheeled).
- Applies commander constraints (arrival deadlines, slope caps, distance limits) to select the best option.
- Exports GPX, GeoJSON, and a Markdown mission brief with per-route checksums; includes `@nav/brief` prompt template.
- Surfaces provenance with TTL tracking for local map datasets.
- Offers both JSON-RPC (stdin/stdout) MCP server and a scripted CLI orchestrator.

## Project Layout

```
data/                # Local raster/vector fixtures (DEM, landcover, roads, obstacles)
exports/             # Created at runtime for GPX/GeoJSON/brief outputs
route_planner_mcp/   # Application package (tools, MCP server, CLI)
```

## Architecture Overview

```mermaid
flowchart TD
    Client[CLI / MCP host / route-planner-tool] -->|JSON-RPC (stdin/stdout)| Server[FastMCP server<br/>route_planner_mcp.server]
    Server -->|Loads fixtures| Data[(Local DEM<br/>landcover<br/>roads<br/>obstacles)]
    Server -->|A* search + terrain metrics| Pathfinding[Route generation<br/>profiles: balanced / trail_pref / low_exposure]
    Server --> Risk[Risk engine<br/>slope / exposure / hydrology]
    Server --> Pace[Pace estimator<br/>Naismith + load/mode]
    Server --> Selection[Selection policy<br/>constraints / policy id]
    Selection --> Exports[Exporter<br/>GeoJSON / GPX / brief<br/>SHA-256 checksums]
    Exports --> Files[exports/ directory]
```

## Getting Started

### 1. Install dependencies

```bash
python -m venv env
source env/bin/activate
pip install -e .
```

### 2. Run the MCP server

```bash
route-planner-mcp-server
```

The server is implemented with FastMCP and automatically exposes MCP tool metadata following the official guidance.[^fastmcp] Available methods:

- `nav.route`
- `nav.risk_eval`
- `nav.pace_estimator`
- `nav.select`
- `nav.export`
- `@nav/brief` (prompt metadata via `list_prompts`)

### 3. Call an individual tool (no manual JSON required)

Use the helper CLI to handle the JSON-RPC handshake automatically (no need to start the server yourself):

```bash
route-planner-tool nav.route --args '{"start":[34.001,-116.999],"end":[34.008,-116.992],"max_candidates":3}'
```

Swap `nav.route` for any other tool (e.g. `nav.risk_eval`, `nav.export`) and adjust `--args` to match the required parameters.

Call other tools the same way:

```bash
# Evaluate risk for specific routes (IDs returned by nav.route)
route-planner-tool nav.risk_eval --args '{"route_ids":["route-1","route-2"]}'

# Estimate pace for cached routes (omit route_ids to use all)
route-planner-tool nav.pace_estimator --args '{"mode":"foot","load_kg":20,"route_ids":["route-1","route-2"]}'

# Select the preferred route under commander constraints
route-planner-tool nav.select --args '{
  "route_ids":["route-1","route-2"],
  "prefer_low_risk": true,
  "avoid_slope_degrees": 12,
  "max_distance_m": 1500
}'

# Export the chosen route bundle (call nav.select first)
route-planner-tool nav.export --args '{"basename":"mission-blue"}'
```

> Tip: Do **not** run `route-planner-mcp-server` in the same terminal while using `route-planner-tool`. The helper spawns and shuts down the FastMCP server behind the scenes for each call.

### Alternative: Launch via MCP CLI

If you prefer to run through the `mcp` helper (which takes care of the JSON-RPC handshake), use:

```bash
source env/bin/activate
mcp run route-planner-mcp-server.py
```

That adapter script simply calls the same FastMCP app, so the JSON responses are identical.

### 4. Use the planner CLI

The CLI orchestrates `route → risk → pace → select → export`.

```bash
route-planner-cli \
  --start 34.001 -116.999 \
  --end 34.008 -116.992 \
  --mode foot \
  --load-kg 20 \
  --export-name mission-red
```

Outputs include pace/risk summaries (with weighting breakdown) and relative export paths with SHA-256 checksums rooted at `exports/`.

Responses also carry a `schema` fingerprint, EPSG:4326 CRS metadata, and an explicit `waypoints_in_gpx` flag confirming checkpoint parity in device exports.

Call `nav.export` directly (or supply `--export-name`) to choose the basename for generated `*.geojson`, `*.gpx`, and brief files; defaults to the selected route id.

## Prompt Metadata

`@nav/brief` is exposed via `list_prompts`. Agents can request the template to compose Markdown mission briefs summarizing checkpoints, timing, and risk caveats.

## Data Provenance & TTLs

Each tool response exposes dataset freshness. DEM and landcover expire after 30 days. Agents should re-run planning steps if TTL flags appear expired.

## Development

- Run `pytest` (when tests are added) with `pip install .[dev]`.
- Lint via `ruff`/`black` or preferred tooling (not bundled).
- Update fixtures in `data/` to reflect new AOIs or intelligence; keep metadata timestamps current to pass TTL checks.

[^fastmcp]: Based on the “Build an MCP server” guide.[Model Context Protocol – Build an MCP server](https://modelcontextprotocol.io/docs/develop/build-server)
