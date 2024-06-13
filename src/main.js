const { app, BrowserWindow, ipcMain } = require('electron/main');
const path = require('node:path');
const { execFile } = require('child_process');
const http = require('http');
const fs = require('fs');

let serverProcess;

const createWindow = () => {
  const win = new BrowserWindow({
    width: 800,
    height: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  win.loadFile('src/index.html');
};

app.whenReady().then(() => {
  ipcMain.handle('ping', () => 'pong');
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });

  // Start the FastAPI server
  const serverExecutable = process.platform === 'win32'
    ? path.join(__dirname, '..', 'dist', 'server.exe')
    : path.join(__dirname, '..', 'dist', 'server');

  serverProcess = execFile(serverExecutable, (error, stdout, stderr) => {
    if (error) {
      console.error(`Error: ${error.message}`);
      return;
    }
    if (stderr) {
      console.error(`stderr: ${stderr}`);
      return;
    }
    console.log(`stdout: ${stdout}`);
  });

  ipcMain.handle('api-request', async (event, endpoint) => {
    return new Promise((resolve, reject) => {
      const options = {
        hostname: "127.0.0.1",
        port: 7725,
        path: endpoint,
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      };

      const req = http.request(options, (res) => {
        let data = '';

        res.on('data', (chunk) => {
          data += chunk;
        });

        res.on('end', () => {
          resolve(JSON.parse(data));
        });
      });

      req.on('error', (e) => {
        reject(`Problem with request: ${e.message}`);
      });

      req.end();
    });
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }

  if (serverProcess) {
    serverProcess.kill();
  }
});
