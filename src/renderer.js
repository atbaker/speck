const func = async () => {
    const response = await window.versions.ping();
    console.log(response); // prints out 'pong'
  };
  
  func();
  
  document.getElementById('fetch-hello-python').addEventListener('click', async () => {
    const response = await window.api.fetchHelloPython();
    console.log(response);
    document.getElementById('output').innerText = response.output;
  });
  