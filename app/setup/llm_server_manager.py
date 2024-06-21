import os
import subprocess
import threading
import time
import requests

from config import cache, settings


class LLMServerManager:
    def __init__(self):
        self.lock = threading.Lock()

    def _read_state(self):
        state = cache.get('llm_server_state')

        if state is None:
            return {"pid": None, "usage_count": 0}
        return state

    def _write_state(self, state):
        cache.set('llm_server_state', state)

    def start_llamafile_process(self):
        model_path = os.path.join(settings.models_dir, 'Meta-Llama-3-8B-Instruct.Q4_0.gguf')

        try:
            process = subprocess.Popen(
                ['sh', settings.llamafile_exe_path, '--server', '--nobrowser', '--port', '7726', '--model', model_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Poll the /health endpoint until the server is ready
            health_url = "http://127.0.0.1:7726/health"
            for _ in range(60):  # Retry for up to 60 seconds
                try:
                    response = requests.get(health_url)
                    if response.status_code == 200 and response.json().get("status") == "ok":
                        return process
                except requests.RequestException:
                    pass
                time.sleep(1)

            # If the server did not become ready in time, kill the process
            process.terminate()
            print("Error: Model server did not become ready in time.")
            return None

        except Exception as e:
            print(f"Error starting model server: {e}")
            return None

    def start_server(self):
        with self.lock:
            state = self._read_state()
            if not state["pid"] or not self._is_process_running(state["pid"]):
                process = self.start_llamafile_process()
                if process:
                    state["pid"] = process.pid
                    state["usage_count"] = 1
                    self._write_state(state)
                    return process.pid
                else:
                    return None  # Return early if the server couldn't be started

            state["usage_count"] += 1
            self._write_state(state)
            return state["pid"]

    def stop_server(self):
        """Stop the server if it's not being used."""
        with self.lock:
            state = self._read_state()
            state["usage_count"] -= 1
            if state["usage_count"] <= 0 and state["pid"]:
                try:
                    os.kill(state["pid"], 15)  # Terminate the process
                    state["pid"] = None
                    state["usage_count"] = 0
                    print("Server stopped.")
                except ProcessLookupError:
                    print("Server process not found.")

            self._write_state(state)

    def force_stop_server(self):
        """Forcefully stop the server."""
        with self.lock:
            state = self._read_state()
            if state["pid"]:
                try:
                    os.kill(state["pid"], 15)  # Attempt to terminate the process gracefully
                    time.sleep(5)  # Wait for a few seconds to allow graceful termination
                    if self._is_process_running(state["pid"]):
                        os.kill(state["pid"], 9)  # Forcefully kill the process if still running
                    state["pid"] = None
                    state["usage_count"] = 0
                    print("Server forcefully stopped.")
                except ProcessLookupError:
                    print("Server process not found.")
            self._write_state(state)

    def _is_process_running(self, pid):
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

llm_server_manager = LLMServerManager()
