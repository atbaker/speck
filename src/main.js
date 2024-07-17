const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron/main');
const axios = require('axios');
const path = require('node:path');
const { execFile, exec } = require('child_process');
const { URL } = require('url');
const log = require('electron-log');

// Use the user application data directory for the log path
log.transports.file.resolvePathFn = (variables) => {
  return path.join(app.getPath('userData'), 'logs', variables.fileName);
}

log.initialize();
log.info('Starting Speck...');

let serverProcess;

const createLogger = (name, fileName) => {
  const logger = log.create(name);
  logger.transports.file.resolvePathFn = (variables) => {
    return path.join(app.getPath('userData'), 'logs', fileName);
  };
  return logger;
};

const launchProcess = (logFileName) => {
  const logger = createLogger('speck', logFileName);

  const executablePath = process.platform === 'win32'
    ? path.join(app.getAppPath(), '../speck', 'speck.exe')
    : path.join(app.getAppPath(), '../speck', 'speck');

  const options = {
    stdio: ['ignore', 'pipe', 'pipe'],
    execArgv: ['--title=speck'], // Set the process title
    env: {
      ...process.env, // Inherit existing environment variables
      APP_DATA_DIR: app.getPath('userData') // Set the custom environment variable
    }
  };
  let processInstance;

  try {
    processInstance = execFile(executablePath, [], options);

    if (processInstance.pid) {
      log.info(`speck process started with PID: ${processInstance.pid}`);
    } else {
      throw new Error(`speck process failed to start`);
    }

    processInstance.stdout.on('data', (data) => {
      logger.info(data.toString());
    });

    processInstance.stderr.on('data', (data) => {
      logger.error(data.toString());
    });

    processInstance.on('close', (code) => {
      logger.info(`speck process exited with code ${code}`);
    });

  } catch (error) {
    log.error(`Failed to start speck process: ${error.message}`);
  }

  return processInstance;
};

let mainWindow;

const createWindow = () => {
  if (mainWindow) {
    mainWindow.focus();
    return;
  }

  mainWindow = new BrowserWindow({
    width: 800,
    height: 600,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  mainWindow.loadFile('src/index.html');

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
};

const gotTheLock = app.requestSingleInstanceLock();

if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', (event, commandLine, workingDirectory) => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
    // Handle deep link URL
    const url = commandLine.pop();
    log.info('Received deep link URL:', url);
    if (url.startsWith('speck://receive-oauth-code')) {
      const parsedUrl = new URL(url);
      const code = parsedUrl.searchParams.get('code');
      forwardOAuthCode(code);
    }
  });

  app.whenReady().then(() => {
    if (!app.requestSingleInstanceLock()) {
      app.quit();
      return;
    }

    ipcMain.handle('ping', () => 'pong');
    ipcMain.handle('start-auth', async () => {
      shell.openExternal('https://atbaker.ngrok.io/authorize');
    });
    ipcMain.handle('get-tokens', async () => {
      return tokens;
    });

    log.info("User data path: ", app.getPath('userData'));

    createWindow();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
      }
    });

    // Register custom protocol
    app.setAsDefaultProtocolClient('speck');

    if (app.isPackaged) {
      serverProcess = launchProcess('speck.log');
    } else {
      log.info('Skipping speck start in development mode');
    }
  });

  app.on('before-quit', () => {
    if (serverProcess) {
      log.info('Killing speck process...');
      if (process.platform === 'win32') {
        exec(`taskkill /F /T /PID ${serverProcess.pid}`, (error, stdout, stderr) => {
          if (error) {
            log.error(`Failed to kill speck process: ${error.message}`);
          } else {
            log.info(`Speck process killed: ${stdout}`);
          }
        });
      } else {
        serverProcess.kill();
      }
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
}