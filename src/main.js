const { app, BrowserWindow, ipcMain, shell } = require('electron/main');
const path = require('node:path');
const { execFile } = require('child_process');
const { URL } = require('url');
const log = require('electron-log');

log.initialize();
log.info('Starting Speck...');

let serverProcess;
let tokens = {};

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

  // Start the FastAPI server TODO: Fix in production to use pyinstaller executable
  // ? path.join(__dirname, '../..', 'server', 'server.exe')
  // : path.join(__dirname, '../..', 'server', 'server');
  const serverExecutable = process.platform === 'win32'
    ? 'python'
    : 'python3';
  const serverArgs = ['-m', 'services.server'];

  serverProcess = execFile(serverExecutable, serverArgs, (error, stdout, stderr) => {
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

// Handle the 'open-url' event on macOS
app.on('open-url', (event, url) => {
  log.info('open-url event triggered')
  event.preventDefault();
  const parsedUrl = new URL(url);
  tokens.accessToken = parsedUrl.searchParams.get('access_token');
  tokens.refreshToken = parsedUrl.searchParams.get('refresh_token');
  // If you want to display the tokens immediately, you might want to send a message to the renderer process here
  if (BrowserWindow.getAllWindows().length > 0) {
    const mainWindow = BrowserWindow.getAllWindows()[0];
    mainWindow.webContents.send('tokens-updated', tokens);
  }
});
