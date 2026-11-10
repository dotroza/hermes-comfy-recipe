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
      const emptyOpenPointers = [];
      for (const storage of [localStorage, sessionStorage]) {
        for (let i = 0; i < storage.length; i++) {
          const key = storage.key(i);
          if (key?.startsWith('Comfy.Workflow.DraftIndex.v2:')) {
            const index = JSON.parse(storage.getItem(key));
            if (index && Array.isArray(index.order) && index.order.length === 0 &&
                index.entries && Object.keys(index.entries).length === 0) continue;
          }
          if (key?.startsWith('Comfy.Workflow.OpenPaths:') ||
              key === 'Comfy.Workflow.LastOpenPaths:personal') {
            const pointer = JSON.parse(storage.getItem(key));
            if (pointer?.workspaceId === 'personal' && Array.isArray(pointer.paths) &&
                pointer.paths.length === 0 && pointer.activeIndex === -1) {
              emptyOpenPointers.push([storage, key]);
              continue;
            }
          }
          if (legacy.has(key) || [
                'Comfy.Workflow.DraftIndex.v2:', 'Comfy.Workflow.Draft.v2:',
                'Comfy.Workflow.ActivePath:', 'Comfy.Workflow.OpenPaths:',
                'Comfy.Workflow.LastActivePath:', 'Comfy.Workflow.LastOpenPaths:'
              ].some(prefix => key?.startsWith(prefix)) ||
              key?.startsWith('Comfy.PreviousWorkflow:') ||
              key?.startsWith('Comfy.OpenWorkflowsPaths:') || key?.startsWith('workflow:')) {
            return;
          }
        }
      }
      const paths = __WORKFLOW_PATHS__;
      const openPointer = JSON.stringify({workspaceId: 'personal', paths, activeIndex: 0});
      localStorage.setItem('Comfy.Workflow.LastOpenPaths:personal', openPointer);
      // Native restore prefers session pointers: an empty bootstrap pointer must
      // not shadow the first-launch localStorage fallback. Write only after all
      // storage has been checked for real restored tabs or drafts.
      for (const [storage, key] of emptyOpenPointers) storage.setItem(key, openPointer);
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
