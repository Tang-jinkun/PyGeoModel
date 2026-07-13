import { describe, expect, it, vi } from "vitest";

import { MODEL_REGISTRY } from "../models/registry";
import type { OutputFile, TaskSummary } from "../models/shared";
import type { UavMetrics, UavRequest } from "../models/uav/types";
import { useMapWorkspace } from "./useMapWorkspace";

describe("useMapWorkspace", () => {
  it("provides immutable point and waypoint commands with undo and clear", () => {
    const workspace = useMapWorkspace("point-or-route");
    const first: [number, number] = [79.8, 31.4];
    workspace.pickPoint(first);
    first[0] = 0;
    workspace.appendWaypoint([79.9, 31.5]);
    workspace.moveWaypoint(1, [80, 32]);

    expect(workspace.draft.value.points).toEqual([[79.8, 31.4], [80, 32]]);
    workspace.removeWaypoint(0);
    workspace.undo();
    expect(workspace.draft.value.points).toHaveLength(2);
    workspace.clear();
    expect(workspace.draft.value.points).toHaveLength(0);
  });

  it("focuses GeoJSON bounds through the supplied map", () => {
    const workspace = useMapWorkspace("point");
    const fitBounds = vi.fn();
    const focused = workspace.focusBounds({ fitBounds } as never, {
      type: "Point",
      coordinates: [79.8, 31.4]
    });

    expect(focused).toBe(true);
    expect(fitBounds).toHaveBeenCalledOnce();
  });

  it("loads a GeoJSON layer from download_url before url", async () => {
    const metrics = vi.fn().mockResolvedValue({});
    const output: OutputFile = {
      kind: "visible_geojson",
      label: "Visible coverage",
      url: "/view-visible",
      download_url: "/download-visible",
      filename: "visible.geojson",
      media_type: "application/geo+json",
      exists: true
    };
    const outputs = vi.fn().mockResolvedValue([output]);
    const fetchGeoJson = vi.fn().mockResolvedValue({ type: "FeatureCollection", features: [] });
    const workspace = useMapWorkspace("point-or-route", undefined, {
      clientFactory: () => ({ metrics, outputs }),
      fetchGeoJson
    });
    const task: TaskSummary<UavRequest, UavMetrics> = {
      task_id: "uav-download-url",
      status: "finished",
      progress: 100,
      message: "分析完成",
      request: MODEL_REGISTRY.uav.createDefaultRequest(),
      metrics: null,
      output_files: [],
      warnings: []
    };

    await workspace.loadTaskOutputs("uav", task);

    expect(fetchGeoJson).toHaveBeenCalledOnce();
    expect(fetchGeoJson).toHaveBeenCalledWith("/download-visible");
  });
});
