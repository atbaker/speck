# Speck

**Speck is an open-source, privacy-first local AI agent application.**

Speck is currently a proof-of-concept. This README will be expanded soon with instructions on how to run Speck yourself. In the meantime, if you have questions about Speck, [reach out to me and I'll be happy to chat](https://www.linkedin.com/in/andrewtorkbaker/).

## Quickstart

TODO: write after first release

## Install and run Speck from source

Follow these instructions to install and run Speck from its source code.

Before following these instructions, make sure you've installed [Node.js](https://nodejs.org/en/learn/getting-started/how-to-install-nodejs) and [Python](https://docs.python-guide.org/starting/installation/) on your machine, as well as the Python package manager [Poetry](https://python-poetry.org/).

### Install the dependencies

1. [Clone this repository](https://github.com/atbaker/speck) to a directory on your machine

2. Install the Node.js dependencies for the Speck Electron app:

```
npm install
```

3. Next, the Node dependencies for the Speck browser extension:

```
cd extension
npm install
```

4. Now, install the Python dependencies using Poetry:

```
cd .. # if you are in the extension directory
cd speck-server
poetry install
```

5. Finally, download [the latest Llamafile release](https://github.com/Mozilla-Ocho/llamafile/releases/latest) and make it executable:

**On macOS and \*nix**

Download the latest Llamafile binary, move it to `speck/speck-server/speck`, and make it executable with `chmod +x speck/speck-server/speck/llamafile`.

**On Windows**

Download the latest Llamafile binary, move it to `speck/speck-server/speck/llamafile`, and rename it to `llamafile.exe`.

### Run Speck without building a release

To run Speck unpackaged in your local development environment, you need to start Speck's Python service and then start the Electron app. After that, you will install the Speck browser extension.

**Start Speck's Python service**

1. Activate a new shell / terminal session in your Poetry environment:

```
poetry shell
```

2. Start the Speck Python service:

```
cd speck-server
python speck/main.py
```

Upon starting for the first time, you should see log entries as Speck gets to work downloading a local copy of its LLM and preparing a browser it can use for executing Speck Functions.

You can confirm that your Speck Python service are working correctly by visiting http://localhost:17725/ in your browser.

**Start the Speck Electron app**

Staring the Electron app is more straightforward. From the root directory of the repo, run:

```
npm run start
```

The Speck Electron app should automatically open. You can confirm that the Speck Electron process is correctly communicating with the Speck Python service by clicking the "Connect Speck to your inbox" button, starting the Google OAuth flow.

**Install the Speck browser extension**

Speck uses a browser extension to enhance the Gmail UI, which is how you'll use most Speck features.

So far, I have tested the browser extension on Firefox and Chrome. To load the extension in your own browser, start by running the appropriate build command:

To build for Firefox:

```
cd extension
npm run build:firefox
```

or, to build for Chrome:

```
cd extension
npm run build:chrome
```

After you build the extension for your target browser, load it as a temporary / unpacked extension:

[From Firefox's docs](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Your_first_WebExtension#installing):

> Open the [about:debugging](https://firefox-source-docs.mozilla.org/devtools-user/about_colon_debugging/index.html) page, click the This Firefox option, click the Load Temporary Add-on button, then select any file in your extension's directory. The extension now installs, and remains installed until you restart Firefox.

[From Chrome's docs](https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world#load-unpacked):

> Go to the Extensions page by entering chrome://extensions in a new tab. Alternatively, click the Extensions menu puzzle button and select Manage Extensions at the bottom of the menu. Or, click the Chrome menu, hover over More Tools, then select Extensions. Enable Developer Mode by clicking the toggle switch next to Developer mode. Click the Load unpacked button and select the extension directory.

Congrats! 🎉

You've finished setting up your Speck development environment. You can now edit Speck source code and see your changes live when you restart the Python process, the Electron process, or reload your browser extension.

### Package a Speck application (optional)

To package your local Speck environment into a full, standalone application, follow these instructions:

**Build the Speck Python service**

Speck uses [PyInstaller](https://pyinstaller.org/en/stable/) to bundle the Python application code into an executable.

From within your active Poetry shell, run:

```
cd speck-server
pyinstaller speck.spec
```

You can confirm the process succeeded by checking the `speck-server/dist` directory: you should see a binary called `speck` and a directory called `_internal`.

**Make an Electron build**

After building the Python service, you can then run the make command to build the complete Electron application, which will include the Python build we just created.

```
cd .. # if you're in the speck-server directory
npm run make
```

You should spot a new directory in the top level of your repo, `out`, which contains both a built version of your Speck application and a `make` directory, which is a fully packaged version of the same application.

And that's it! You can now open your Speck application and use it just like if you had downloaded and installed a normal Speck release.
