let actions = [];

console.log("Recording script loaded");

// Add event listeners to record user actions
document.addEventListener("click", (event) => {
  actions.push({
    type: "click",
    timestamp: Date.now(),
    x: event.clientX,
    y: event.clientY,
    target: event.target.outerHTML
  });
  console.log("Actions:", actions);
});

document.addEventListener("input", (event) => {
  actions.push({
    type: "input",
    timestamp: Date.now(),
    target: event.target.outerHTML,
    value: event.target.value
  });
  console.log("Actions:", actions);
});