from diskcache import Lock
import logging
import os
import subprocess
import time
import requests
import platform
import psutil
import threading
from functools import wraps

from config import cache, settings

logger = logging.getLogger(__name__)


class LLMServiceManager:
    def __init__(self):
        pass

    def _get_state(self):
        state = cache.get('llm_service_state')
        if state is None:
            state = {
                'embedding': {'pid': None, 'usage_count': 0, 'shutdown_scheduled': False},
                'completion': {'pid': None, 'usage_count': 0, 'shutdown_scheduled': False}
            }
            cache.set('llm_service_state', state)
        return state

    def _set_state(self, state):
        cache.set('llm_service_state', state)

    def _start_inference_process(self, model_type):
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
            service_port = '17727'
            model_path = os.path.join(settings.models_dir, 'Meta-Llama-3.1-8B-Instruct-Q4_K_S.gguf')
            context_size = '10240'

            process_args = [
                settings.llamafile_exe_path,
                '--server',
                '--nobrowser',
                '--port',
                service_port,
                '-ngl', # TODO: Not sure if this would be worse than CPU inference on weak GPUs
                '9999',
                '--ctx-size',
                context_size,
                '--model',
                model_path
            ]
        else:
            raise ValueError(f"Invalid model type: {model_type}. Must be 'embedding' or 'completion'")

        # Define separate log files for each model type
        stdout_log_path = os.path.join(settings.log_dir, f'{model_type}_stdout.log')
        stderr_log_path = os.path.join(settings.log_dir, f'{model_type}_stderr.log')

        # Start the process with lower priority on macOS
        if settings.os_name == 'Darwin':
            process_args = ['nice', '-n', '10'] + process_args

        try:
            with open(stdout_log_path, 'a') as stdout_log, open(stderr_log_path, 'a') as stderr_log:
                process = subprocess.Popen(
                    process_args,
                    stdout=stdout_log,
                    stderr=stderr_log,
                    text=True
                )

            # Set the process to have low priority on Windows
            if settings.os_name == 'Windows':
                p = psutil.Process(process.pid)
                p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        except Exception as e:
            logger.error(f"Error starting {model_type} server: {e}")
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
                # For the completion server, we need to check both for a 200
                # status code and a "status": "ok" field in the response body
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
        with Lock(cache, 'llm_service_lock'):
            state = self._get_state()
            model_state = state[model_type]

            if not model_state["pid"] or not self._is_process_running(model_state["pid"]):
                process = self._start_inference_process(model_type)
                if process:
                    model_state["pid"] = process.pid
                    model_state["usage_count"] = 1
                    model_state["shutdown_scheduled"] = False
                    self._set_state(state)
                    return process.pid
                else:
                    return None  # Return early if the server couldn't be started
            else:
                model_state["usage_count"] += 1
                # Cancel any existing shutdown schedule
                if model_state.get('shutdown_scheduled'):
                    model_state['shutdown_scheduled'] = False
                self._set_state(state)
                return model_state["pid"]

    def stop_server(self, model_type='embedding'):
        with Lock(cache, 'llm_service_lock'):
            state = self._get_state()
            model_state = state[model_type]
            model_state["usage_count"] -= 1
            if model_state["usage_count"] <= 0:
                model_state["usage_count"] = 0
                if not model_state.get('shutdown_scheduled'):
                    model_state['shutdown_scheduled'] = True
                    model_state["last_used_time"] = time.time()
                    threading.Thread(target=self._check_idle_server, args=(model_type,), daemon=True).start()
            self._set_state(state)

    def _check_idle_server(self, model_type):
        time.sleep(5)  # Wait for the idle timeout
        with Lock(cache, 'llm_service_lock'):
            state = self._get_state()
            model_state = state[model_type]
            idle_time = time.time() - model_state.get("last_used_time", 0)
            if model_state["usage_count"] == 0 and idle_time >= 5:
                if model_state["pid"]:
                    try:
                        if platform.system() == "Windows":
                            self._terminate_process_windows(model_state["pid"])
                        else:
                            os.kill(model_state["pid"], 15)  # Terminate the process
                        logger.info(f"Llamafile {model_type} server stopped due to inactivity.")
                    except ProcessLookupError:
                        logger.error(f"Tried to stop Llamafile {model_type} server but process not found.")
                    model_state["pid"] = None
                # No need to close logs here
            model_state['shutdown_scheduled'] = False
            self._set_state(state)

    def force_stop(self):
        """Forcefully stop all inference servers."""
        with Lock(cache, 'llm_service_lock'):
            state = self._get_state()
            for model_type in ['embedding', 'completion']:
                model_state = state[model_type]
                if model_state["pid"]:
                    try:
                        if platform.system() == "Windows":
                            self._terminate_process_windows(model_state["pid"])
                        else:
                            os.kill(model_state["pid"], 15)
                            time.sleep(5)
                            if self._is_process_running(model_state["pid"]):
                                os.kill(model_state["pid"], 9)
                        logger.info(f"{model_type} server forcefully stopped.")
                    except (ProcessLookupError, psutil.NoSuchProcess):
                        logger.warning(f"{model_type} server process not found during force stop.")
                    except Exception as e:
                        logger.error(f"Error force stopping {model_type} server: {e}")
                    finally:
                        model_state["pid"] = None
                        model_state["usage_count"] = 0
                        model_state['shutdown_scheduled'] = False
                else:
                    logger.info(f"{model_type} server was not running.")
            self._set_state(state)

    def _terminate_process_windows(self, pid):
        try:
            process = psutil.Process(pid)
            process.terminate()
            process.wait(5)
        except Exception as e:
            logger.error(f"Error terminating process on Windows: {e}")

    def _is_process_running(self, pid):
        try:
            process = psutil.Process(pid)
            return process.is_running()
        except Exception:
            return False

llm_service_manager = LLMServiceManager()

def use_local_inference_service(model_type='embedding'):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # For 'completion', check if local completions are enabled
            if model_type == 'completion' and not settings.use_local_completions:
                return func(*args, **kwargs)

            pid = llm_service_manager.start_server(model_type)
            if not pid:
                raise RuntimeError("Failed to start the inference service.")

            try:
                result = func(*args, **kwargs)
            finally:
                llm_service_manager.stop_server(model_type)
            return result

        return wrapper
    return decorator
