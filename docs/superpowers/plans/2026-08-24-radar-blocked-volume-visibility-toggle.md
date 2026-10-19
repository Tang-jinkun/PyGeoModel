# 雷达遮挡体独立显隐 Implementation Plan

> For agentic workers: use superpowers:executing-plans to implement this plan task-by-task with checkpoints.

**Goal:** Add a frontend-only “遮挡” toggle that hides or shows red terrain-occluded GLB meshes without changing green meshes, scan slices, APIs, or GLB files.

**Architecture:** prepareStaticScene collects meshes identified by blocked_volume or terrain_occluded. The scene adapter and workspace carry blockedVisible state plus a post-load blockedAvailable capability. sceneGlbLayer toggles only the collected mesh set, and WorkbenchDock renders a per-scene checkbox only when a loaded GLB reports blocked meshes.

**Tech Stack:** Vue 3, TypeScript, Three.js, MapLibre custom layers, Vitest, Vue Test Utils.

## Global Constraints

- Do not add API request fields or change task/output interfaces.
- Keep red semantic materials color-locked and keep scan visibility independent.
- Default blockedVisible to true.
- Historical GLBs without blocked meshes load normally and do not show an enabled “遮挡” control.
- Preserve all unrelated dirty worktree changes.

---

### Task 1: Collect and render blocked meshes independently

**Files:**
- Modify: frontend/src/map/sceneGlbAsset.ts
- Modify: frontend/src/map/sceneGlbLayer.ts
- Test: frontend/src/map/sceneGlbAsset.test.ts
- Test: frontend/src/map/sceneGlbLayer.test.ts

**Interfaces:**
- PreparedSceneGlb.blockedNodes: THREE.Object3D[] contains every blocked mesh.
- SceneGlbLayerOptions.blockedVisible?: boolean defaults to true.
- Export setSceneGlbLayerBlockedVisibility(map, taskId, visible): boolean.

- [ ] Step 1: Write the failing asset test.

Extend the existing blocked-volume fixture with two blocked meshes and assert:

    expect(asset.blockedNodes.map((node) => node.name)).toEqual([
      "radar_result/blocked_volume",
      "radar_result/blocked_volume_side"
    ]);

Add a legacy fixture with only detectable_shell and assert blockedNodes is empty.

- [ ] Step 2: Run the asset test and verify RED.

Run:

    Set-Location frontend
    npm exec vitest run src/map/sceneGlbAsset.test.ts

Expected: failure because PreparedSceneGlb has no blockedNodes field and the collection assertion fails.

- [ ] Step 3: Implement minimal asset collection.

Add blockedNodes to PreparedSceneGlb, initialize it in prepareStaticScene, and push each prepared mesh when userData.kind is blocked_volume or userData.visibility_semantics is terrain_occluded. Reuse one local isBlockedMesh helper for collection, red material locking, and render-order assignment.

- [ ] Step 4: Write the failing layer test.

Add two blocked nodes to the existing prepared scene fixture and assert:

    expect(setSceneGlbLayerBlockedVisibility(map as never, "task-a", false)).toBe(true);
    expect(asset.blockedNodes.map((node) => node.visible)).toEqual([false, false]);
    expect(asset.scanNodes.map((node) => node.visible)).toEqual([true, true]);
    expect(asset.group.getObjectByName("radar_result/detectable_shell")?.visible).toBe(true);

Then toggle true again, and assert an unregistered task returns false.

- [ ] Step 5: Run the layer test and verify RED.

Run:

    Set-Location frontend
    npm exec vitest run src/map/sceneGlbLayer.test.ts

Expected: failure because the blocked visibility export and managed-layer method do not exist.

- [ ] Step 6: Implement minimal layer control.

Add blockedVisible to SceneGlbLayerOptions and setBlockedVisibility to ManagedCustomLayer. In createCustomLayer, apply blockedVisible only to asset.blockedNodes during onAdd and expose setSceneGlbLayerBlockedVisibility through the registry. Repaint only when the asset has blocked nodes.

- [ ] Step 7: Run both map tests and verify GREEN.

Run:

    Set-Location frontend
    npm exec vitest run src/map/sceneGlbAsset.test.ts src/map/sceneGlbLayer.test.ts

Expected: all tests in both files pass.

### Task 2: Carry blocked capability and state through the workspace

**Files:**
- Modify: frontend/src/composables/useMapWorkspace.ts
- Test: frontend/src/composables/useMapWorkspace.test.ts

**Interfaces:**
- SceneGlbOverlayState.blockedVisible: boolean defaults to true.
- SceneGlbOverlayState.blockedAvailable: boolean defaults to false.
- SceneGlbLoadRequest.blockedVisible: boolean and onBlockedAvailability(available: boolean): void.
- SceneGlbAdapter.setBlockedVisibility?(map, taskId, visible): boolean.
- Workspace method setSceneGlbBlockedVisibility(map, taskId, kind, visible): boolean.

- [ ] Step 1: Write the failing workspace tests.

Extend the scene adapter mock with setBlockedVisibility. Make the load mock call request.onBlockedAvailability(true), then assert the state reports blockedAvailable true, blockedVisible true, the load request contains blockedVisible true, and calling setSceneGlbBlockedVisibility(..., false) changes only blockedVisible and invokes the adapter without changing scanVisible. Add a legacy case calling onBlockedAvailability(false) and assert blockedAvailable remains false.

- [ ] Step 2: Run the workspace tests and verify RED.

Run:

    Set-Location frontend
    npm exec vitest run src/composables/useMapWorkspace.test.ts

Expected: failure because the new state fields, request callback, and workspace method do not exist.

- [ ] Step 3: Implement workspace state and callback.

Initialize blockedVisible true and blockedAvailable false in ensureSceneGlbState. Pass blockedVisible and an onBlockedAvailability callback into sceneGlb.load, guarding callback updates so an obsolete controller cannot mutate current state. Add setSceneGlbBlockedVisibility to persist the requested value and delegate to sceneGlb.setBlockedVisibility. Wire DEFAULT_SCENE_GLB_ADAPTER to report asset.blockedNodes.length > 0 and pass blockedVisible into addSceneGlbLayer.

- [ ] Step 4: Run the workspace tests and verify GREEN.

Run:

    Set-Location frontend
    npm exec vitest run src/composables/useMapWorkspace.test.ts

Expected: all workspace tests pass.

### Task 3: Add the “遮挡” control to the workbench panel

**Files:**
- Modify: frontend/src/components/workbench/WorkbenchDock.vue
- Test: frontend/src/components/workbench/WorkbenchDock.test.ts

**Interfaces:**
- WorkbenchDock emits update-scene-glb-blocked(entryId: string, visible: boolean).
- Scene rows render data-scene-glb-blocked only when entry.state.blockedAvailable is true.

- [ ] Step 1: Write the failing component test.

Set blockedAvailable true and blockedVisible true in the ready scene fixture. Toggle the new checkbox and assert:

    expect(wrapper.emitted("update-scene-glb-blocked")?.[0]).toEqual([
      "task-1:scene_glb",
      false
    ]);

Add a legacy fixture with blockedAvailable false and assert the checkbox does not exist.

- [ ] Step 2: Run the component test and verify RED.

Run:

    Set-Location frontend
    npm exec vitest run src/components/workbench/WorkbenchDock.test.ts

Expected: failure because the event and checkbox are not rendered.

- [ ] Step 3: Implement the panel control.

Declare the update-scene-glb-blocked event and render a compact checkbox next to the scan checkbox. Use an aria-label built from entry.file.label plus “地形遮挡”, data-scene-glb-blocked, and emit the entry id plus checked value. Keep it separate from scan and adjust only the scene-row grid needed for the extra control.

- [ ] Step 4: Run the component test and verify GREEN.

Run:

    Set-Location frontend
    npm exec vitest run src/components/workbench/WorkbenchDock.test.ts

Expected: all component tests pass and legacy rows have no blocked checkbox.

### Task 4: Wire App events and complete verification

**Files:**
- Modify: frontend/src/App.vue
- Test: existing frontend component/workspace coverage; add an App test only if event wiring is not covered by the existing scene-entry path.

**Interfaces:**
- App.vue handles update-scene-glb-blocked and delegates using the scene entry taskId and kind.
- Single-radar, aggregate fusion, and cooperative station assets all use the existing workbenchSceneEntries mapping.

- [ ] Step 1: Add the App event handler.

Add update-scene-glb-blocked to the WorkbenchDock binding and implement setWorkbenchSceneBlockedVisibility:

    function setWorkbenchSceneBlockedVisibility(entryId: string, visible: boolean) {
      const instance = map.value;
      const entry = workbenchSceneEntries.value.find((candidate) => candidate.id === entryId);
      if (instance && entry) {
        mapWorkspace.setSceneGlbBlockedVisibility(instance, entry.taskId, entry.kind, visible);
      }
    }

Do not modify setWorkbenchSceneScanVisibility.

- [ ] Step 2: Run the complete frontend test suite.

Run:

    Set-Location frontend
    npm test -- --run

Expected: zero failed tests.

- [ ] Step 3: Run the production build.

Run:

    Set-Location frontend
    npm run build

Expected: exit code 0. Existing runtime-config and chunk-size warnings may remain, but no TypeScript or Vite errors.

- [ ] Step 4: Review the final diff.

Run:

    Set-Location E:\Github\PyGeoModel
    git diff --check
    git status --short

Confirm only intended frontend files are changed and do not stage or alter pre-existing logs, .tools, frontend redesign files, or coverage_task.py.

