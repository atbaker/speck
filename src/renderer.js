const func = async () => {
  const response = await window.versions.ping();
  console.log(response); // prints out 'pong'
};

func();

document.getElementById('start-auth').addEventListener('click', async () => {
  await window.versions.startAuth();
});

document.getElementById('get-tokens').addEventListener('click', async () => {
  const tokens = await window.versions.getTokens();
  console.log(tokens);
  document.getElementById('output').innerText = JSON.stringify(tokens, null, 2);
});

window.api.receive('tokens-updated', (event, tokens) => {
  document.getElementById('output').innerText = JSON.stringify(tokens, null, 2);
});
