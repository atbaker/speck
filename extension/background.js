const browser = require('webextension-polyfill');

// Check if the browser is Chrome or Firefox
if (typeof browser === 'undefined') {
    var browser = chrome;
}

// If running in Chrome, load the service worker
if (browser.runtime.getManifest().background.service_worker) {
    browser.runtime.registerServiceWorker('background-sw.js');
} else {
    // Otherwise, implement the same logic as the service worker directly for Firefox
    browser.runtime.onInstalled.addListener(() => {
        console.log('Extension installed');
    });

    // Add more event listeners here, just like you would in the service worker
    browser.webRequest.onBeforeRequest.addListener(
        (details) => {
            console.log('Request intercepted:', details);
            // Add your logic here
        },
        { urls: ["<all_urls>"] }
    );
}
