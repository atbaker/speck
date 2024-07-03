const { app, BrowserWindow, ipcMain, shell } = require('electron/main');
const axios = require('axios');
const path = require('node:path');
const { execFile } = require('child_process');
const { URL } = require('url');
const log = require('electron-log');

// Use the user application data directory for the log path
log.transports.file.resolvePathFn = (variables) => {
  return path.join(app.getPath('userData'), 'logs', variables.fileName);
}

log.initialize();
log.info('Starting Speck...');

let serverProcess;
let workerProcess;
let schedulerProcess;

const createLogger = (name, fileName) => {
  const logger = log.create(name);
  logger.transports.file.resolvePathFn = (variables) => {
    return path.join(app.getPath('userData'), 'logs', fileName);
  };
  return logger;
};

const launchProcess = (executableName, logFileName) => {
  const logger = createLogger(executableName, logFileName);

  const executablePath = process.platform === 'win32'
    ? path.join(app.getAppPath(), '../services', `${executableName}.exe`)
    : path.join(app.getAppPath(), '../services', executableName);

  const args = [`--user-data-dir=${app.getPath('userData')}`];
  let processInstance;

  try {
    processInstance = execFile(executablePath, args, {
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    if (processInstance.pid) {
      log.info(`${executableName} process started with PID: ${processInstance.pid}`);
    } else {
      throw new Error(`${executableName} process failed to start`);
    }

    processInstance.stdout.on('data', (data) => {
      logger.info(data.toString());
    });

    processInstance.stderr.on('data', (data) => {
      logger.error(data.toString());
    });

    processInstance.on('close', (code) => {
      logger.info(`${executableName} process exited with code ${code}`);
    });

  } catch (error) {
    log.error(`Failed to start ${executableName} process: ${error.message}`);
  }

  return processInstance;
};

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
    serverProcess = launchProcess('speck-server', 'server.log');
    workerProcess = launchProcess('speck-worker', 'worker.log');
    schedulerProcess = launchProcess('speck-scheduler', 'scheduler.log');
  } else {
    log.info('Skipping server and worker start in development mode');
  }
});

app.on('before-quit', () => {
  if (serverProcess) {
    log.info('Killing server process...');
    serverProcess.kill();
  }
  if (workerProcess) {
    log.info('Killing worker process...');
    workerProcess.kill();
  }
  if (schedulerProcess) {
    log.info('Killing scheduler process...');
    schedulerProcess.kill();
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
