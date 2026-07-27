import { readonly, ref, watch, type Ref } from "vue";

export type DockTab = "catalog" | "layers" | "data";
export type TaskCenterTab = "running" | "history" | "logs";
export type InspectorMode = "parameters" | "result";

export function useWorkbenchPresentation(selectedTaskKey: Readonly<Ref<string | null>>) {
  const dockTab = ref<DockTab>("catalog");
  const taskTab = ref<TaskCenterTab>("running");
  const taskCenterCollapsed = ref(false);
  const inspectorMode = ref<InspectorMode>("parameters");

  watch(selectedTaskKey, (taskKey) => {
    if (taskKey) inspectorMode.value = "result";
  });

  function selectDockTab(tab: DockTab) {
    dockTab.value = tab;
  }

  function selectTaskTab(tab: TaskCenterTab) {
    taskTab.value = tab;
  }

  function toggleTaskCenter() {
    taskCenterCollapsed.value = !taskCenterCollapsed.value;
  }

  function selectModel() {
    inspectorMode.value = "parameters";
  }

  function selectTask() {
    inspectorMode.value = "result";
    dockTab.value = "layers";
  }

  function showParameters() {
    inspectorMode.value = "parameters";
  }

  return {
    dockTab: readonly(dockTab),
    taskTab: readonly(taskTab),
    taskCenterCollapsed: readonly(taskCenterCollapsed),
    inspectorMode: readonly(inspectorMode),
    selectDockTab,
    selectTaskTab,
    toggleTaskCenter,
    selectModel,
    selectTask,
    showParameters
  };
}
