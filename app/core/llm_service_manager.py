import logging
import os
import subprocess
import threading
import time
import requests
from functools import wraps
import platform
import psutil

from config import settings
from core.cache import cache

logger = logging.getLogger(__name__)


class LLMServiceManager:
    def __init__(self):
        self.stdout_log = None
        self.stderr_log = None

    def _read_state(self):
        state = cache.get('llm_service_state')

        if state is None:
            return {"pid": None, "usage_count": 0}
        return state

    def _write_state(self, state):
        cache.set('llm_service_state', state)

    def start_llamafile_process(self):
        # model_path = os.path.join(settings.models_dir, 'Meta-Llama-3-8B-Instruct.Q4_0.gguf')
        model_path = os.path.join(settings.models_dir, 'gemma-2-9b-it-Q6_K.gguf')
        # model_path = os.path.join(settings.models_dir, 'Phi-3-mini-4k-instruct-q4.gguf')

        self.stdout_log = open(os.path.join(settings.log_dir, 'llamafile_stdout.log'), 'a')
        self.stderr_log = open(os.path.join(settings.log_dir, 'llamafile_stderr.log'), 'a')

        llamafile_process_args = [
            settings.llamafile_exe_path,
            '--server',
            '--nobrowser',
            '--port',
            '7726',
            '-ngl', # TODO: Not sure if this has bad side effects when running on a machine without a GPU / with a crummy GPU
            '9999',
            '--no-mmap', # Gemma 2 has weird behavior when using mmap :shrug:
            '--ctx-size',
            '8192', # 8k context window for Llama 3 and Gemma 2
            # '4096', # 4k context window for Phi 3
            '--model',
            model_path
        ]

        if settings.os_name == 'Darwin':
            llamafile_process_args = ['sh'] + llamafile_process_args

        try:
            process = subprocess.Popen(
                llamafile_process_args,
                stdout=self.stdout_log,
                stderr=self.stderr_log,
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
            logger.error("Error: Model server did not become ready in time.")
            return None

        except Exception as e:
            logger.error(f"Error starting model server: {e}")
            return None

    def start_server(self):
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
        state = self._read_state()
        state["usage_count"] -= 1
        if state["usage_count"] <= 0 and state["pid"]:
            try:
                if platform.system() == "Windows":
                    self._terminate_process_windows(state["pid"])
                else:
                    os.kill(state["pid"], 15)  # Terminate the process

                state["pid"] = None
                state["usage_count"] = 0
                logger.info("Llamafile server stopped.")
            except ProcessLookupError:
                logger.error("Tried to stop Llamafile server but process not found.")

        try:
            self.stdout_log.close()
            self.stderr_log.close()
        except AttributeError:
            pass

        self._write_state(state)

    def force_stop_server(self):
        """Forcefully stop the server."""
        state = self._read_state()
        if state["pid"]:
            try:
                if platform.system() == "Windows":
                    self._terminate_process_windows(state["pid"])
                else:
                    os.kill(state["pid"], 15)  # Attempt to terminate the process gracefully
                    time.sleep(5)  # Wait for a few seconds to allow graceful termination
                    if self._is_process_running(state["pid"]):
                        os.kill(state["pid"], 9)  # Forcefully kill the process if still running

                state["pid"] = None
                state["usage_count"] = 0
                logger.info("Llamafile server forcefully stopped.")
            except ProcessLookupError:
                logger.error("Tried to force stop Llamafile server but process not found.")

        try:
            self.stdout_log.close()
            self.stderr_log.close()
        except AttributeError as e:
            pass

        self._write_state(state)

    def _terminate_process_windows(self, pid):
        try:
            process = psutil.Process(pid)
            process.terminate()
            process.wait(5)  # Wait for the process to terminate
        except Exception as e:
            logger.error(f"Error terminating process on Windows: {e}")

    def _is_process_running(self, pid):
        if platform.system() == "Windows":
            try:
                process = psutil.Process(pid)
                return process.is_running()
            except Exception:
                return False
        else:
            try:
                os.kill(pid, 0)
            except OSError:
                return False
            return True

llm_service_manager = LLMServiceManager()

def use_inference_service(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        pid = llm_service_manager.start_server()
        if not pid:
            raise RuntimeError("Failed to start the inference service.")
        
        try:
            result = func(*args, **kwargs)
        finally:
            threading.Timer(5, llm_service_manager.stop_server).start()
        
        return result
    
    return wrapper
