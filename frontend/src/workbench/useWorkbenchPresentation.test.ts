import { ref } from "vue";
import { describe, expect, it } from "vitest";

import { useWorkbenchPresentation } from "./useWorkbenchPresentation";

describe("useWorkbenchPresentation", () => {
  it("switches to result detail after a task selection and returns to parameters on request", async () => {
    const selectedTaskKey = ref<string | null>(null);
    const presentation = useWorkbenchPresentation(selectedTaskKey);

    expect(presentation.inspectorMode.value).toBe("parameters");

    selectedTaskKey.value = "radar:task-8";
    await Promise.resolve();
    expect(presentation.inspectorMode.value).toBe("result");

    presentation.showParameters();
    expect(presentation.inspectorMode.value).toBe("parameters");

    presentation.selectTask();
    expect(presentation.inspectorMode.value).toBe("result");
    expect(presentation.dockTab.value).toBe("layers");
  });

  it("keeps dock and task-center presentation state independent", () => {
    const presentation = useWorkbenchPresentation(ref<string | null>(null));

    presentation.selectDockTab("layers");
    presentation.selectTaskTab("logs");
    presentation.toggleTaskCenter();

    expect(presentation.dockTab.value).toBe("layers");
    expect(presentation.taskTab.value).toBe("logs");
    expect(presentation.taskCenterCollapsed.value).toBe(true);
  });
});
