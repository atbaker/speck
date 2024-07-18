const browser = require('webextension-polyfill');

browser.runtime.onInstalled.addListener(() => {
    console.log('Speck Gmail Extension background service worker installed');
});
