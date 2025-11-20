"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { LngLatBounds, Map } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useForm } from "react-hook-form";
import { useMutation } from "@tanstack/react-query";

import {
  PlanRequest,
  PlanResponse,
  TerrainBundleSummary,
  createPlan,
  fetchTerrainBundles,
  uploadTerrainBundle,
} from "@/lib/api";

type LineFeature = GeoJSON.Feature<GeoJSON.LineString>;

const ROUTE_SOURCE_ID = "routes-source";
const ROUTE_LAYER_ID = "routes-layer";

const defaultPayload: PlanRequest = {
  terrain_id: ".",
  start_lat: 34.001,
  start_lon: -116.999,
  end_lat: 34.008,
  end_lon: -116.992,
  preference: "balanced",
  policy: "prefer_low_risk",
  mode: "foot",
  load_kg: 20,
};

export default function HomePage() {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const [isMapReady, setMapReady] = useState(false);
  const [terrainBundles, setTerrainBundles] = useState<TerrainBundleSummary[]>(
    [],
  );
  const [lastRequest, setLastRequest] = useState<PlanRequest | null>(
    defaultPayload,
  );
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState("");
  const [uploadDescription, setUploadDescription] = useState("");
  const [uploadProgress, setUploadProgress] = useState<{
    status: string;
    message: string;
    progress: number;
  } | null>(null);
  const [planningStatus, setPlanningStatus] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { isSubmitting },
    setValue,
  } = useForm<PlanRequest>({
    defaultValues: defaultPayload,
  });

  // Update terrain_id when bundles are loaded
  useEffect(() => {
    if (
      terrainBundles.length > 0 &&
      !terrainBundles.find((b) => b.id === ".")
    ) {
      setValue("terrain_id", terrainBundles[0].id);
    }
  }, [terrainBundles, setValue]);

  const planMutation = useMutation({
    mutationFn: async (payload: PlanRequest) => {
      setPlanningStatus("Loading terrain data...");
      await new Promise((resolve) => setTimeout(resolve, 300));

      setPlanningStatus("Analyzing terrain and finding paths...");
      await new Promise((resolve) => setTimeout(resolve, 300));

      const result = await createPlan(payload);

      setPlanningStatus("Evaluating route options...");
      await new Promise((resolve) => setTimeout(resolve, 300));

      setPlanningStatus(null);

      return { result, payload } as {
        result: PlanResponse;
        payload: PlanRequest;
      };
    },
    onSuccess: ({ payload }) => {
      setLastRequest(payload);
      setPlanningStatus(null);
    },
    onError: () => {
      setPlanningStatus(null);
    },
  });

  const uploadMutation = useMutation({
    mutationFn: async ({
      file,
      name,
      description,
    }: {
      file: File;
      name: string;
      description?: string;
    }) => {
      try {
        const response = await uploadTerrainBundle(file, name, description);
        console.log("Upload response:", response);

        // Poll for progress
        if (response.upload_id) {
          let completed = false;
          while (!completed) {
            await new Promise((resolve) => setTimeout(resolve, 1000));

            try {
              const statusResponse = await fetch(
                `http://localhost:8000/api/v1/terrain/upload/${response.upload_id}/status`,
              );

              if (!statusResponse.ok) {
                throw new Error(
                  `Status check failed: ${statusResponse.status}`,
                );
              }

              const status = await statusResponse.json();
              console.log("Upload status:", status);
              setUploadProgress(status);

              if (status.status === "completed") {
                completed = true;
                if (status.bundle) {
                  setTerrainBundles((prev) => [...prev, status.bundle]);
                }
              } else if (status.status === "error") {
                completed = true;
                throw new Error(status.message);
              }
            } catch (statusError) {
              console.error("Status polling error:", statusError);
              throw statusError;
            }
          }
        }

        return response;
      } catch (error) {
        console.error("Upload mutation error:", error);
        throw error;
      }
    },
    onSuccess: () => {
      setTimeout(() => {
        setShowUploadModal(false);
        setUploadFile(null);
        setUploadName("");
        setUploadDescription("");
        setUploadProgress(null);
        loadTerrainBundles(); // Reload the list
      }, 2000);
    },
    onError: (error) => {
      console.error("Upload error:", error);
      setUploadProgress({
        status: "error",
        message: error instanceof Error ? error.message : "Upload failed",
        progress: 0,
      });
      setTimeout(() => {
        setUploadProgress(null);
      }, 5000);
    },
  });

  const loadTerrainBundles = () => {
    fetchTerrainBundles()
      .then(setTerrainBundles)
      .catch(() => {
        setTerrainBundles([]);
      });
  };

  useEffect(() => {
    loadTerrainBundles();
  }, []);

  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) {
      return;
    }

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: {
        version: 8,
        sources: {
          "dark-tiles": {
            type: "raster",
            tiles: [
              "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
              "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
              "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
            ],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors, © CARTO",
          },
          "osm-labels": {
            type: "vector",
            tiles: ["https://tiles.openfreemap.org/planet/{z}/{x}/{y}.pbf"],
            attribution: "© OpenStreetMap contributors",
            maxzoom: 14,
          },
        },
        glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
        layers: [
          {
            id: "dark-background",
            type: "raster",
            source: "dark-tiles",
            minzoom: 0,
            maxzoom: 22,
          },
          {
            id: "place-labels",
            type: "symbol",
            source: "osm-labels",
            "source-layer": "place",
            filter: ["in", "class", "country", "state", "city", "town"],
            layout: {
              "text-field": ["get", "name"],
              "text-font": ["Noto Sans Regular"],
              "text-size": [
                "interpolate",
                ["linear"],
                ["zoom"],
                2,
                10,
                6,
                14,
                10,
                18,
              ],
              "text-transform": "uppercase",
              "text-letter-spacing": 0.05,
              "text-max-width": 8,
            },
            paint: {
              "text-color": "#e0e0e0",
              "text-halo-color": "#1a1a1a",
              "text-halo-width": 1.5,
              "text-halo-blur": 1,
            },
          },
        ],
      },
      center: [0, 20],
      zoom: 2,
    });

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }));
    map.on("load", () => setMapReady(true));
    mapRef.current = map;

    return () => {
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current = [];
      map.remove();
      mapRef.current = null;
      setMapReady(false);
    };
  }, []);
  useEffect(() => {
    const map = mapRef.current;
    if (map && isMapReady) {
      map.resize();
    }
  }, [isMapReady]);

  const routes = useMemo(() => {
    const payload = planMutation.data?.result.route_payload;
    return payload?.routes ?? [];
  }, [planMutation.data]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isMapReady) {
      return;
    }

    if (map.getLayer(ROUTE_LAYER_ID)) {
      map.removeLayer(ROUTE_LAYER_ID);
    }
    if (map.getSource(ROUTE_SOURCE_ID)) {
      map.removeSource(ROUTE_SOURCE_ID);
    }

    const features: LineFeature[] = routes
      .filter((route) => route.steps && route.steps.length > 1)
      .map((route) => ({
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates:
            route.steps?.map((step) => [
              step.coordinate[1],
              step.coordinate[0],
            ]) ?? [],
        },
        properties: {
          id: route.id,
        },
      }));

    if (!features.length) {
      return;
    }

    map.addSource(ROUTE_SOURCE_ID, {
      type: "geojson",
      data: {
        type: "FeatureCollection",
        features,
      },
    });

    map.addLayer({
      id: ROUTE_LAYER_ID,
      type: "line",
      source: ROUTE_SOURCE_ID,
      paint: {
        "line-color": [
          "case",
          ["==", ["get", "id"], routes[0]?.id ?? ""],
          "#34d399",
          "#38bdf8",
        ],
        "line-width": 3.5,
      },
    });

    const bounds = new LngLatBounds();
    features.forEach((feature) => {
      feature.geometry.coordinates.forEach((coord) =>
        bounds.extend(coord as [number, number]),
      );
    });
    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, { padding: 60, maxZoom: 14 });
    }
  }, [routes, isMapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !lastRequest || !isMapReady) {
      return;
    }

    markersRef.current.forEach((marker) => marker.remove());
    markersRef.current = [];

    const startMarker = new maplibregl.Marker({ color: "#22c55e" })
      .setLngLat([lastRequest.start_lon, lastRequest.start_lat])
      .addTo(map);
    const endMarker = new maplibregl.Marker({ color: "#ef4444" })
      .setLngLat([lastRequest.end_lon, lastRequest.end_lat])
      .addTo(map);

    markersRef.current = [startMarker, endMarker];
  }, [lastRequest, isMapReady]);

  const toNumber = (value: unknown, fallback: number): number => {
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
    const parsed = parseFloat(String(value));
    return Number.isFinite(parsed) ? parsed : fallback;
  };

  const onSubmit = handleSubmit((values) => {
    console.log("Form values received:", values);
    // Force number conversion - handle both undefined and string values
    const parseNum = (val: any, fallback: number) => {
      const num = typeof val === "string" ? parseFloat(val) : val;
      return Number.isFinite(num) ? num : fallback;
    };

    const payload: PlanRequest = {
      ...values,
      load_kg: parseNum(values.load_kg, defaultPayload.load_kg),
      start_lat: parseNum(values.start_lat, defaultPayload.start_lat),
      start_lon: parseNum(values.start_lon, defaultPayload.start_lon),
      end_lat: parseNum(values.end_lat, defaultPayload.end_lat),
      end_lon: parseNum(values.end_lon, defaultPayload.end_lon),
    };
    console.log("Converted payload:", payload);
    planMutation.reset();
    planMutation.mutate(payload);
  });

  const llmBrief = planMutation.data?.result.llm_brief ?? "";

  return (
    <main className="relative flex h-screen w-screen flex-col overflow-hidden bg-gradient-to-b from-slate-950 to-slate-900">
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-emerald-900/20 via-slate-900 to-slate-900" />

      {/* Upload Progress Toast */}
      {uploadProgress && (
        <div className="fixed top-6 right-6 z-50 w-96 rounded-xl border border-emerald-500/60 bg-slate-900/95 p-4 shadow-2xl backdrop-blur">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                {uploadProgress.status === "completed" ? (
                  <span className="text-lg">✅</span>
                ) : uploadProgress.status === "error" ? (
                  <span className="text-lg">❌</span>
                ) : (
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-emerald-400 border-t-transparent" />
                )}
                <h3 className="font-semibold text-white">
                  {uploadProgress.status === "completed"
                    ? "Upload Complete"
                    : uploadProgress.status === "error"
                      ? "Upload Failed"
                      : "Processing Upload"}
                </h3>
              </div>
              <p className="mt-2 text-sm text-slate-300">
                {uploadProgress.message}
              </p>
              {uploadProgress.status !== "completed" &&
                uploadProgress.status !== "error" && (
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                      <span>Progress</span>
                      <span>{uploadProgress.progress}%</span>
                    </div>
                    <div className="w-full bg-slate-700 rounded-full h-2">
                      <div
                        className="bg-emerald-400 h-2 rounded-full transition-all duration-500"
                        style={{ width: `${uploadProgress.progress}%` }}
                      />
                    </div>
                    {uploadProgress.progress === 20 && (
                      <p className="mt-2 text-xs text-emerald-300/70">
                        Large files can take 5-15 minutes. Please wait...
                      </p>
                    )}
                  </div>
                )}
            </div>
            {uploadProgress.status !== "completed" &&
            uploadProgress.status !== "error" ? null : (
              <button
                onClick={() => setUploadProgress(null)}
                className="ml-2 text-slate-400 hover:text-slate-200"
              >
                <svg
                  className="h-5 w-5"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            )}
          </div>
        </div>
      )}

      <div className="relative z-10 grid h-full max-h-screen grid-cols-1 gap-6 overflow-hidden p-6 lg:grid-cols-[minmax(24rem,30rem)_minmax(0,1fr)] lg:grid-rows-[minmax(0,1fr)_minmax(0,1fr)]">
        <section className="flex flex-col gap-6 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/60 p-6 shadow-lg lg:col-start-1 lg:row-start-1">
          <header>
            <h1 className="text-2xl font-semibold text-white">
              Mission Route Planner
            </h1>
            <p className="mt-2 text-sm text-slate-300">
              Plan tactical routes with terrain analysis. The system evaluates
              candidate paths and provides recommendations for mission approval.
            </p>
          </header>

          <form
            onSubmit={onSubmit}
            className="space-y-4 text-sm text-slate-200"
          >
            <div>
              <div className="flex items-center justify-between">
                <label className="block text-xs uppercase tracking-wide text-slate-400">
                  Terrain bundle
                </label>
                <button
                  type="button"
                  onClick={() => setShowUploadModal(true)}
                  className="text-xs text-emerald-400 hover:text-emerald-300"
                >
                  + Upload
                </button>
              </div>
              <select
                className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
                {...register("terrain_id")}
              >
                {terrainBundles.length === 0 ? (
                  <option value="">No terrain bundles available</option>
                ) : (
                  terrainBundles.map((bundle) => (
                    <option key={bundle.id} value={bundle.id}>
                      {bundle.name}
                    </option>
                  ))
                )}
              </select>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs uppercase tracking-wide text-slate-400">
                  Start latitude
                  <input
                    type="number"
                    step="0.0001"
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
                    {...register("start_lat", { valueAsNumber: true })}
                  />
                </label>
              </div>
              <div>
                <label className="block text-xs uppercase tracking-wide text-slate-400">
                  Start longitude
                  <input
                    type="number"
                    step="0.0001"
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
                    {...register("start_lon", { valueAsNumber: true })}
                  />
                </label>
              </div>
              <div>
                <label className="block text-xs uppercase tracking-wide text-slate-400">
                  End latitude
                  <input
                    type="number"
                    step="0.0001"
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
                    {...register("end_lat", { valueAsNumber: true })}
                  />
                </label>
              </div>
              <div>
                <label className="block text-xs uppercase tracking-wide text-slate-400">
                  End longitude
                  <input
                    type="number"
                    step="0.0001"
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
                    {...register("end_lon", { valueAsNumber: true })}
                  />
                </label>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs uppercase tracking-wide text-slate-400">
                  Preference
                </label>
                <select
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
                  {...register("preference")}
                >
                  <option value="balanced">Balanced</option>
                  <option value="trail_pref">Prefer trails</option>
                  <option value="low_exposure">Limit exposure</option>
                </select>
              </div>

              <div>
                <label className="block text-xs uppercase tracking-wide text-slate-400">
                  Policy
                </label>
                <select
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
                  {...register("policy")}
                >
                  <option value="prefer_low_risk">Prefer low risk</option>
                  <option value="cost_only">Cost only</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs uppercase tracking-wide text-slate-400">
                  Load (kg)
                  <input
                    type="number"
                    min={0}
                    step="1"
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
                    {...register("load_kg", { valueAsNumber: true })}
                  />
                </label>
              </div>
              <div>
                <label className="block text-xs uppercase tracking-wide text-slate-400">
                  Mode
                </label>
                <select
                  className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
                  {...register("mode")}
                >
                  <option value="foot">Foot</option>
                  <option value="wheeled">Wheeled</option>
                </select>
              </div>
            </div>

            {planningStatus && (
              <div className="rounded border border-blue-500/60 bg-blue-500/10 px-3 py-3 flex items-center gap-3">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-blue-400 border-t-transparent" />
                <span className="text-sm text-blue-200">{planningStatus}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={isSubmitting || planMutation.isPending}
              className="w-full rounded border border-emerald-400 bg-emerald-500/10 px-4 py-2 text-sm font-medium text-emerald-200 transition hover:bg-emerald-400/20 disabled:border-slate-700 disabled:bg-slate-800 disabled:text-slate-500"
            >
              {planMutation.isPending ? "Planning route…" : "Plan route"}
            </button>
            {planMutation.isError ? (
              <p className="rounded border border-rose-500/60 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                {(planMutation.error as Error).message}
              </p>
            ) : null}
          </form>
        </section>

        <section className="relative flex flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900/60 shadow-lg lg:col-start-2 lg:row-start-1">
          <div ref={mapContainerRef} className="h-full w-full" />
          {!isMapReady ? (
            <div className="pointer-events-none absolute inset-0 flex items-center justify-center bg-slate-900/70 text-sm text-slate-200">
              Loading map…
            </div>
          ) : null}
        </section>

        <section className="flex flex-col gap-4 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/60 p-6 shadow-lg lg:col-start-1 lg:row-start-2">
          <div className="rounded-lg border border-slate-800 bg-slate-900/80 p-4">
            <h2 className="text-sm font-semibold text-white">
              Mission Assessment
            </h2>
            {planMutation.isPending ? (
              <p className="mt-2 text-xs text-slate-300">
                Analyzing terrain and route options…
              </p>
            ) : llmBrief ? (
              <div className="mt-2 space-y-2 text-sm text-slate-200">
                {llmBrief
                  .split("\n")
                  .map((paragraph, idx) =>
                    paragraph.trim() ? <p key={idx}>{paragraph}</p> : null,
                  )}
              </div>
            ) : (
              <p className="mt-2 text-xs text-slate-400">
                Plan a route to view mission assessment and recommendations.
              </p>
            )}
          </div>
        </section>

        <section className="flex flex-col overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/60 p-6 shadow-lg lg:col-start-2 lg:row-start-2">
          <div className="rounded-lg border border-slate-800 bg-slate-900/80 p-4">
            <h2 className="text-sm font-semibold text-white">Route Analysis</h2>
            {routes.length > 0 ? (
              <div className="mt-3 overflow-hidden rounded-lg border border-slate-800">
                <table className="min-w-full divide-y divide-slate-800 text-sm text-slate-200">
                  <thead className="bg-slate-900/80 text-xs uppercase text-slate-400">
                    <tr>
                      <th className="px-3 py-2 text-left">Route</th>
                      <th className="px-3 py-2 text-left">Distance (km)</th>
                      <th className="px-3 py-2 text-left">Estimated cost</th>
                      <th className="px-3 py-2 text-left">Trail km</th>
                      <th className="px-3 py-2 text-left">Open km</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800 bg-slate-900/40">
                    {routes.map((route, idx) => (
                      <tr
                        key={route.id}
                        className={
                          idx === 0
                            ? "bg-emerald-500/10 text-emerald-200"
                            : undefined
                        }
                      >
                        <td className="px-3 py-2 font-medium">{route.id}</td>
                        <td className="px-3 py-2">
                          {(route.distance_m / 1000).toFixed(2)}
                        </td>
                        <td className="px-3 py-2">
                          {route.estimated_cost.toFixed(3)}
                        </td>
                        <td className="px-3 py-2">
                          {route.coverage?.trail
                            ? route.coverage.trail.toFixed(3)
                            : "—"}
                        </td>
                        <td className="px-3 py-2">
                          {route.coverage?.open
                            ? route.coverage.open.toFixed(3)
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="mt-2 text-xs text-slate-400">
                Plan a route to analyze and compare candidate paths.
              </p>
            )}
          </div>
        </section>

        {/* Upload Modal */}
        {showUploadModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
            <div className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 p-6 shadow-xl">
              <h2 className="text-xl font-semibold text-white">
                Upload Terrain Data
              </h2>
              <p className="mt-2 text-sm text-slate-300">
                Upload terrain archive (.zip, .tar.gz) or OpenStreetMap data
                (.osm.pbf)
              </p>

              <div className="mt-4 space-y-4">
                <div>
                  <label className="block text-xs uppercase tracking-wide text-slate-400">
                    Terrain Name
                  </label>
                  <input
                    type="text"
                    value={uploadName}
                    onChange={(e) => setUploadName(e.target.value)}
                    placeholder="e.g., Mountain Region"
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-emerald-400 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs uppercase tracking-wide text-slate-400">
                    Description (optional)
                  </label>
                  <input
                    type="text"
                    value={uploadDescription}
                    onChange={(e) => setUploadDescription(e.target.value)}
                    placeholder="Brief description"
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 focus:border-emerald-400 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs uppercase tracking-wide text-slate-400">
                    Terrain File
                  </label>
                  <input
                    type="file"
                    accept=".zip,.tar.gz,.tgz,.pbf,.osm.pbf"
                    onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                    className="mt-1 w-full rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-200 file:mr-4 file:rounded file:border-0 file:bg-emerald-500/10 file:px-4 file:py-1 file:text-sm file:text-emerald-200 hover:file:bg-emerald-400/20 focus:border-emerald-400 focus:outline-none"
                  />
                  <p className="mt-1 text-xs text-slate-400">
                    Accepts terrain bundles (.zip) or OpenStreetMap data
                    (.osm.pbf from Geofabrik)
                  </p>
                  {uploadFile && uploadFile.size > 1024 * 1024 * 1024 && (
                    <p className="mt-2 rounded border border-amber-500/60 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                      ⚠️ Large file (
                      {(uploadFile.size / (1024 * 1024 * 1024)).toFixed(1)} GB)
                      - processing may take 10-20 minutes. Consider using a
                      smaller region (state-level instead of multi-state).
                    </p>
                  )}
                </div>

                {uploadProgress && (
                  <div className="rounded border border-emerald-500/60 bg-emerald-500/10 px-3 py-3 space-y-2">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-emerald-200 font-medium">
                        {uploadProgress.status === "completed"
                          ? "✅ "
                          : uploadProgress.status === "error"
                            ? "❌ "
                            : "⏳ "}
                        {uploadProgress.message}
                      </span>
                      <span className="text-emerald-300">
                        {uploadProgress.progress}%
                      </span>
                    </div>
                    {uploadProgress.status !== "completed" &&
                      uploadProgress.status !== "error" && (
                        <div className="w-full bg-slate-700 rounded-full h-1.5">
                          <div
                            className="bg-emerald-400 h-1.5 rounded-full transition-all duration-500"
                            style={{ width: `${uploadProgress.progress}%` }}
                          />
                        </div>
                      )}
                    {uploadProgress.status === "processing" &&
                      uploadProgress.progress === 20 && (
                        <p className="text-xs text-emerald-300/70">
                          Large OSM files can take 5-15 minutes to process.
                          Please wait...
                        </p>
                      )}
                  </div>
                )}

                {uploadMutation.isError && (
                  <p className="rounded border border-rose-500/60 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
                    {(uploadMutation.error as Error).message}
                  </p>
                )}

                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={async () => {
                      if (uploadFile && uploadName) {
                        // Start the upload first
                        uploadMutation.mutate({
                          file: uploadFile,
                          name: uploadName,
                          description: uploadDescription || undefined,
                        });
                        // Wait a bit for the mutation to start, then close modal
                        setTimeout(() => {
                          setShowUploadModal(false);
                        }, 100);
                      }
                    }}
                    disabled={
                      !uploadFile || !uploadName || uploadMutation.isPending
                    }
                    className="flex-1 rounded border border-emerald-400 bg-emerald-500/10 px-4 py-2 text-sm font-medium text-emerald-200 transition hover:bg-emerald-400/20 disabled:border-slate-700 disabled:bg-slate-800 disabled:text-slate-500"
                  >
                    {uploadMutation.isPending ? "Starting..." : "Upload"}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setShowUploadModal(false);
                      setUploadFile(null);
                      setUploadName("");
                      setUploadDescription("");
                      setUploadProgress(null);
                      uploadMutation.reset();
                    }}
                    className="rounded border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 transition hover:bg-slate-700"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

type InputFieldProps = React.InputHTMLAttributes<HTMLInputElement> & {
  label: string;
};

function InputField({ label, ...props }: InputFieldProps) {
  return (
    <label className="block text-xs uppercase tracking-wide text-slate-400">
      {label}
      <input
        className="mt-1 w-full rounded border border-slate-700 bg-slate-900 px-3 py-2 text-sm focus:border-emerald-400 focus:outline-none"
        {...props}
      />
    </label>
  );
}
