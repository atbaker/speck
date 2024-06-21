const { app, BrowserWindow, ipcMain, shell } = require('electron/main');
const axios = require('axios');
const path = require('node:path');
const { execFile } = require('child_process');
const { URL } = require('url');
const log = require('electron-log');

log.initialize();
log.info('Starting Speck...');

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
  ipcMain.handle('start-auth', async () => {
    shell.openExternal('https://atbaker.ngrok.io/authorize');
  });
  ipcMain.handle('get-tokens', async () => {
    return tokens;
  });

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });

  // Register custom protocol
  app.setAsDefaultProtocolClient('speck');

  if (app.isPackaged) {
    const serverExecutable = process.platform === 'win32'
      ? path.join(__dirname, '../..', 'speck', 'speck.exe')
      : path.join(__dirname, '../..', 'speck', 'speck');

    serverProcess = execFile(serverExecutable, {
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    // Log stdout
    serverProcess.stdout.on('data', (data) => {
      log.info(data.toString());
    });

    // Log stderr
    serverProcess.stderr.on('data', (data) => {
      log.error(data.toString());
    });

    serverProcess.on('close', (code) => {
      log.info(`Server process exited with code ${code}`);
    });

  } else {
    log.info('Skipping server start in development mode');
  }
});

app.on('before-quit', () => {
  if (serverProcess) {
    serverProcess.kill()
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
});

// Function to send a Google OAuth code to the FastAPI server for processing
async function forwardOAuthCode(code) {
  try {
    const response = await axios.post('http://127.0.0.1:7725/receive-oauth-code', {
      code: code
    });
    log.info('OAuth code processed successfully:', response.data);
  } catch (error) {
    log.error('Error processing OAuth code:', error);
  }
}

// Handle the 'open-url' event on macOS
app.on('open-url', (event, url) => {
  log.info('open-url event triggered')
  event.preventDefault();
  const parsedUrl = new URL(url);
  if (parsedUrl.pathname === '/receive-oauth-code') {
    const code = parsedUrl.searchParams.get('code');
    forwardOAuthCode(code);
  }
});
