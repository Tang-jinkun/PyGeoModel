import { describe, expect, it } from "vitest";

import { shouldShowRadarPreview } from "./radarPreviewPolicy";

describe("shouldShowRadarPreview", () => {
  it("does not render a draft radar when no analysis task has completed", () => {
    expect(shouldShowRadarPreview(null)).toBe(false);
    expect(shouldShowRadarPreview("running")).toBe(false);
    expect(shouldShowRadarPreview("failed")).toBe(false);
  });

  it("does not render a legacy radar volume after a completed task", () => {
    expect(shouldShowRadarPreview("finished")).toBe(false);
  });
});
