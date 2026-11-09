import { app } from '../../scripts/app.js';

// Seed ComfyUI's native restore pointers before its workflow bootstrap. From then
// on ComfyUI owns these values: never reorder or switch an existing workspace.
app.registerExtension({
  name: 'ComfyRecipe.FirstWorkflow',
  init() {
    try {
      const marker = 'ComfyRecipe.StartupTabs.v1';
      if (localStorage.getItem(marker)) return;
      const legacy = new Set([
        'workflow', 'Comfy.PreviousWorkflow', 'Comfy.OpenWorkflowsPaths',
        'Comfy.ActiveWorkflowIndex', 'Comfy.Workflow.Drafts', 'Comfy.Workflow.DraftOrder'
      ]);
      for (const storage of [localStorage, sessionStorage]) {
        for (let i = 0; i < storage.length; i++) {
          const key = storage.key(i);
          if (key?.startsWith('Comfy.Workflow.DraftIndex.v2:')) {
            const index = JSON.parse(storage.getItem(key));
            if (index && Array.isArray(index.order) && index.order.length === 0 &&
                index.entries && Object.keys(index.entries).length === 0) continue;
          }
          if (legacy.has(key) || key?.startsWith('Comfy.Workflow.') ||
              key?.startsWith('Comfy.PreviousWorkflow:') ||
              key?.startsWith('Comfy.OpenWorkflowsPaths:') || key?.startsWith('workflow:')) {
            return;
          }
        }
      }
      const paths = __WORKFLOW_PATHS__;
      localStorage.setItem('Comfy.Workflow.LastOpenPaths:personal', JSON.stringify({
        workspaceId: 'personal', paths, activeIndex: 0
      }));
      localStorage.setItem('Comfy.Workflow.LastActivePath:personal', JSON.stringify({
        workspaceId: 'personal', path: paths[0]
      }));
      localStorage.setItem(marker, '1');
    } catch (error) {
      // Private/blocked storage must never prevent ComfyUI from starting.
      console.warn('Comfy Recipe: could not initialize workflow tabs', error);
    }
  }
});
