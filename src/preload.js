const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('versions', {
  node: () => process.versions.node,
  chrome: () => process.versions.chrome,
  electron: () => process.versions.electron,
  ping: () => ipcRenderer.invoke('ping'),
  startAuth: () => ipcRenderer.invoke('start-auth'),
  getTokens: () => ipcRenderer.invoke('get-tokens'),
  receive: (channel, func) => {
    const validChannels = ['tokens-updated'];
    if (validChannels.includes(channel)) {
      ipcRenderer.on(channel, func);
    }
  },
});
