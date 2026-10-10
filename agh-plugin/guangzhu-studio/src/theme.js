import manifest from '../extensions/main/skins/agnes.client.json' with {type:'json'};

export function createEmbeddedTheme(win) {
  const root = win.document.documentElement;
  const tokens = manifest.skins.find(skin => skin.id === 'guangzhu').tokens;
  const previous = new Map();
  return {
    apply(mode) {
      if (!['light','dark'].includes(mode)) return;
      for (const name of Object.keys(tokens)) {
        if (!previous.has(name)) previous.set(name,[root.style.getPropertyValue(name),root.style.getPropertyPriority(name)]);
      }
      try {
        win.localStorage.setItem('agnes-theme',mode);
        win.dispatchEvent(new win.StorageEvent('storage',{key:'agnes-theme',newValue:mode,storageArea:win.localStorage}));
      } catch { /* Storage persistence is optional; the current document still receives its theme. */ }
      root.classList.toggle('dark',mode === 'dark');
      // AGH repaints its cached skin synchronously on storage; apply our embedded tokens after it.
      for (const [name,modes] of Object.entries(tokens)) root.style.setProperty(name,modes[mode]);
    },
    dispose() {
      if (!previous.size) return;
      for (const [name,[value,priority]] of previous) {
        if (value) root.style.setProperty(name,value,priority);
        else root.style.removeProperty(name);
      }
      previous.clear();
      try {
        const mode = win.localStorage.getItem('agnes-theme');
        win.dispatchEvent(new win.StorageEvent('storage',{key:'agnes-theme',newValue:mode,storageArea:win.localStorage}));
      } catch { /* Unavailable storage must not prevent removing the embedded overrides. */ }
    },
  };
}
