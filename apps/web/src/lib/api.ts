export type TerrainBundleSummary = {
  id: string;
  name: string;
  description?: string;
};

export type PlanRequest = {
  terrain_id: string;
  start_lat: number;
  start_lon: number;
  end_lat: number;
  end_lon: number;
  preference: "balanced" | "trail_pref" | "low_exposure";
  policy: "prefer_low_risk" | "cost_only";
  mode: "foot" | "wheeled";
  load_kg: number;
  notes?: string | null;
};

export type RouteCandidate = {
  id: string;
  distance_m: number;
  estimated_cost: number;
  coverage?: Record<string, number>;
  steps?: Array<{
    coordinate: [number, number];
    step_type?: string;
    label?: string | null;
  }>;
};

export type PlanResponse = {
  run_id: string;
  llm_brief?: string | null;
  route_payload?: {
    routes?: RouteCandidate[];
  };
};

const DEFAULT_AGENT_URL = "http://localhost:8000";

const AGENT_URL =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_AGENT_URL) ||
  DEFAULT_AGENT_URL;

export async function fetchTerrainBundles(): Promise<TerrainBundleSummary[]> {
  const response = await fetch(
    `${AGENT_URL.replace(/\/$/, "")}/api/v1/terrain`,
  );

  if (!response.ok) {
    // Fallback to empty array if backend is not available
    return [];
  }

  return (await response.json()) as TerrainBundleSummary[];
}

export async function uploadTerrainBundle(
  file: File,
  name: string,
  description?: string,
): Promise<{ upload_id: string; message: string }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("name", name);
  if (description) {
    formData.append("description", description);
  }

  const response = await fetch(
    `${AGENT_URL.replace(/\/$/, "")}/api/v1/terrain/upload`,
    {
      method: "POST",
      body: formData,
    },
  );

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Upload failed with status ${response.status}`);
  }

  return (await response.json()) as { upload_id: string; message: string };
}

// Deprecated: Demo terrain loader
export async function fetchDemoTerrain(): Promise<TerrainBundleSummary[]> {
  return [
    {
      id: ".",
      name: "Demo AOI",
      description: "Sample terrain bundled with the MCP engine",
    },
  ];
}

export async function deleteTerrainBundle(terrainId: string): Promise<void> {
  const response = await fetch(
    `${AGENT_URL.replace(/\/$/, "")}/api/v1/terrain/${terrainId}`,
    {
      method: "DELETE",
    },
  );

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Delete failed with status ${response.status}`);
  }
}

export async function createPlan(payload: PlanRequest): Promise<PlanResponse> {
  const response = await fetch(`${AGENT_URL.replace(/\/$/, "")}/api/v1/plans`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Agent responded with status ${response.status}`);
  }

  return (await response.json()) as PlanResponse;
}
