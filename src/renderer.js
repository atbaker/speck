function startAuth() {
  const url = 'http://localhost:17725/start-google-oauth';
  console.log('starting auth');
  window.electron.openExternal(url);
}

document.getElementById('start-auth').addEventListener('click', startAuth);