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
            return {"embedding": {"pid": None, "usage_count": 0},
                    "completion": {"pid": None, "usage_count": 0}}
        return state

    def _write_state(self, state):
        cache.set('llm_service_state', state)

    def start_llamafile_process(self, model_type):
        if model_type == 'embedding':
            service_port = 17726
            process_args = [
                settings.llamafiler_exe_path,
                '--listen',
                f'127.0.0.1:{service_port}',
                '--model',
                os.path.join(settings.models_dir, 'mxbai-embed-large-v1-f16.gguf')
            ]
        elif model_type == 'completion':
            service_port = 17727
            # model_path = os.path.join(settings.models_dir, 'gemma-2-9b-it-Q5_K_M.gguf')
            # context_size = '8192'
            model_path = os.path.join(settings.models_dir, 'Meta-Llama-3.1-8B-Instruct-Q4_K_S.gguf')
            context_size = '16384'

            process_args = [
                settings.llamafile_exe_path,
                '--server',
                '--nobrowser',
                '--port',
                service_port,
                '-ngl', # TODO: Not sure if this has bad side effects when running on a machine without a GPU / with a crummy GPU
                '9999',
                '--no-mmap',
                '--ctx-size',
                context_size,
                '--model',
                model_path
            ]
        else:
            raise ValueError(f"Invalid model type: {model_type}. Must be 'embedding' or 'completion'")

        self.stdout_log = open(os.path.join(settings.log_dir, 'inference_stdout.log'), 'a')
        self.stderr_log = open(os.path.join(settings.log_dir, 'inference_stderr.log'), 'a')

        # Start the process with lower priority on macOS
        if settings.os_name == 'Darwin':
            process_args = ['nice', '-n', '10'] + process_args

        try:
            process = subprocess.Popen(
                process_args,
                stdout=self.stdout_log,
                stderr=self.stderr_log,
                text=True
            )

            # Set the process to have low priority on Windows
            if settings.os_name == 'Windows':
                p = psutil.Process(process.pid)
                p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)

        except Exception as e:
            logger.error(f"Error starting Llamafile server: {e}")
            return None

        # Poll the server until it is ready
        if model_type == 'embedding':
            health_url = f"http://127.0.0.1:{service_port}/embedding"
            data = {'content': 'healthcheck'}
        else:
            health_url = f"http://127.0.0.1:{service_port}/health"
            data = {}
        for _ in range(60):  # Retry for up to 60 seconds
            try:
                response = requests.get(health_url, params=data)
                # For the completion server, we need to check both for a 200 status code and a "status": "ok" field
                if response.status_code == 200 and response.json().get("status", "ok") == "ok":
                    return process
            except requests.RequestException:
                pass
            time.sleep(1)

        # If the server did not become ready in time, kill the process
        process.terminate()
        logger.error(f"Error: {model_type} server did not become ready in time.")
        return None

    def start_server(self, model_type='embedding'):
        state = self._read_state()
        model_state = state[model_type]
        if not model_state["pid"] or not self._is_process_running(model_state["pid"]):
            process = self.start_llamafile_process(model_type)
            if process:
                model_state["pid"] = process.pid
                model_state["usage_count"] = 1
                self._write_state(state)
                return process.pid
            else:
                return None  # Return early if the server couldn't be started

        model_state["usage_count"] += 1
        self._write_state(state)
        return model_state["pid"]

    def stop_server(self, model_type='embedding'):
        """Stop the server if it's not being used."""
        state = self._read_state()
        model_state = state[model_type]
        model_state["usage_count"] -= 1
        if model_state["usage_count"] <= 0 and model_state["pid"]:
            try:
                if platform.system() == "Windows":
                    self._terminate_process_windows(model_state["pid"])
                else:
                    os.kill(model_state["pid"], 15)  # Terminate the process

                model_state["pid"] = None
                model_state["usage_count"] = 0
                logger.info(f"Llamafile {model_type} server stopped.")
            except ProcessLookupError:
                logger.error(f"Tried to stop Llamafile {model_type} server but process not found.")

        try:
            self.stdout_log.close()
            self.stderr_log.close()
        except AttributeError:
            pass

        self._write_state(state)

    def force_stop_server(self, model_type='embedding'):
        """Forcefully stop the server."""
        state = self._read_state()
        model_state = state[model_type]
        if model_state["pid"]:
            try:
                if platform.system() == "Windows":
                    self._terminate_process_windows(model_state["pid"])
                else:
                    os.kill(model_state["pid"], 15)  # Attempt to terminate the process gracefully
                    time.sleep(5)  # Wait for a few seconds to allow graceful termination
                    if self._is_process_running(model_state["pid"]):
                        os.kill(model_state["pid"], 9)  # Forcefully kill the process if still running

                model_state["pid"] = None
                model_state["usage_count"] = 0
                logger.info(f"Llamafile {model_type} server forcefully stopped.")
            except ProcessLookupError:
                logger.error(f"Tried to force stop Llamafile {model_type} server but process not found.")

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

def use_inference_service(model_type='embedding'):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            pid = llm_service_manager.start_server(model_type)
            if not pid:
                raise RuntimeError("Failed to start the inference service.")

            try:
                result = func(*args, **kwargs)
            finally:
                # Keep the server running for 5 seconds after the function call is finished,
                # in case another task is about to start using it
                threading.Timer(5, llm_service_manager.stop_server, args=[model_type]).start()

            return result

        return wrapper
    return decorator
