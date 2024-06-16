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
    ? path.join(__dirname, '../..', 'server', 'server.exe')
    : path.join(__dirname, '../..', 'server', 'server');

    serverProcess = execFile(serverExecutable, (error, stdout, stderr) => {
      if (error) {
        log.error(`Error: ${error.message}`);
        return;
      }
      if (stderr) {
        log.error(`stderr: ${stderr}`);
        return;
      }
      log.log(`stdout: ${stdout}`);
    });
  } else {
      log.info('Skipping server start in development mode')
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

// Function to send OAuth tokens to the FastAPI server
async function storeOAuthTokens(accessToken, refreshToken) {
  try {
    const response = await axios.post('http://127.0.0.1:7725/store-oauth-tokens', {
      access_token: accessToken,
      refresh_token: refreshToken
    });
    console.log('Tokens stored successfully:', response.data);
  } catch (error) {
    console.error('Error storing tokens:', error);
  }
}

// Handle the 'open-url' event on macOS
app.on('open-url', (event, url) => {
  log.info('open-url event triggered')
  event.preventDefault();
  const parsedUrl = new URL(url);
  const accessToken = parsedUrl.searchParams.get('access_token');
  const refreshToken = parsedUrl.searchParams.get('refresh_token');
  storeOAuthTokens(accessToken, refreshToken);
});
