const func = async () => {
  const response = await window.versions.ping();
  console.log(response); // prints out 'pong'
};

func();

document.getElementById('start-auth').addEventListener('click', async () => {
  await window.versions.startAuth();
});
