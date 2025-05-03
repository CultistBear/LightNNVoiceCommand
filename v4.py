import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # suppress TensorFlow logs

import torch
import sounddevice as sd
import numpy as np
from scipy.io import wavfile
import time
import queue
import threading
import traceback
import pvporcupine
import struct
from constants import MY_API_KEY_PORC as ACCESS_KEY, LATEST_TRAINED
from pymongo import MongoClient
import gridfs
from multiprocessing import Manager, Process
import subprocess
import tempfile
import sys
from transformers import WhisperForConditionalGeneration, WhisperProcessor, logging as hf_logging
import librosa

# Suppress HuggingFace warnings
hf_logging.set_verbosity_error()

# config
WAKE_KEYWORD_PATH = r"C:\Users\singh\Documents\Programs\CapstoneProject\wake-up.ppn"
SHUTDOWN_KEYWORD_PATH = r"C:\Users\singh\Documents\Programs\CapstoneProject\shut-down.ppn"
KEYWORD_PATHS = [WAKE_KEYWORD_PATH, SHUTDOWN_KEYWORD_PATH]
MIN_AUDIO_LENGTH = 0.5
MAX_RECORDING_DURATION = 30

# mongo
client = MongoClient("mongodb://localhost:27017/")
db = client["scripts"]
fs = gridfs.GridFS(db)
metadata_collection = db["file_metadata"]

# Queues and events
audio_queue = queue.Queue()
stop_event = threading.Event()

checkpoint_path = LATEST_TRAINED

def check_keywords(s):
    s= ''.join(e for e in s if e.isalnum())
    found = []
    items = list(metadata_collection.find())
    for item in items:
        if item["keyword"].replace(" ","") in s:
            found.append(item)
    print(found)
    return found

def process_audio():
    processor = WhisperProcessor.from_pretrained(checkpoint_path)
    model = WhisperForConditionalGeneration.from_pretrained(checkpoint_path)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    model.eval()

    if torch.cuda.is_available():
        model.half()

    generation_config = model.generation_config
    generation_config.update(
        suppress_tokens=[],
        forced_decoder_ids=None,
        language="en",
        task="translate"
    )

    while not stop_event.is_set():
        try:
            filename = audio_queue.get(timeout=1)

            if not os.path.exists(filename):
                print(f"File missing: {filename}")
                audio_queue.task_done()
                continue

            audio_array, sampling_rate = librosa.load(filename, sr=16000)
            duration = len(audio_array) / sampling_rate

            if duration < MIN_AUDIO_LENGTH:
                print(f"Skipping short audio ({duration:.1f}s)")
                os.remove(filename)
                audio_queue.task_done()
                continue

            inputs = processor(
                audio_array,
                sampling_rate=sampling_rate,
                return_tensors="pt",
                task="translate"
            ).to(device)

            inputs.input_features = inputs.input_features.to(model.dtype)

            with torch.no_grad():
                predicted_ids = model.generate(
                    inputs.input_features,
                    max_length=448,
                    num_beams=5,
                )

            transcription = processor.batch_decode(
                predicted_ids,
                skip_special_tokens=True
            )[0].lower()

            print(f"\nTranscription: {transcription}\n")
            found_keywords = check_keywords(transcription)
            print()
            for kw in found_keywords:
                print(f"Queueing execution: {kw}")
                execution_queue.put(kw)
            print()

            os.remove(filename)
            audio_queue.task_done()

        except queue.Empty:
            continue
        except Exception as e:
            print(f"\nProcessing error: {str(e)}")
            traceback.print_exc()
            audio_queue.task_done()

def execute_scripts(execution_queue):
    while not stop_event.is_set():
        ext = {"python": "py", "cpp": "cpp", "java": "java",
               "javascript": "js", "shell": "sh", "csharp": "cs"}
        try:
            kw_metadata = execution_queue.get(timeout=1)
            print()
            print(f"Retrieved from execution queue: {kw_metadata}")
            print()
            try:
                file_id = kw_metadata["_id"]
                language = kw_metadata["language"]
                gridfs_file = fs.get(file_id)
                script_content = gridfs_file.read().decode().replace("\xa0", " ")
                print(script_content)

                with tempfile.NamedTemporaryFile(
                    mode='w',
                    suffix=f'.{ext[language]}',
                    delete=False
                ) as temp_file:
                    temp_filename = temp_file.name
                    temp_file.write(script_content)

                print(f"Executing {language.upper()} script: {kw_metadata['keyword']}")

                if language == "python":
                    subprocess.run([sys.executable, temp_filename], check=True)
                elif language == "javascript":
                    subprocess.run(["node", temp_filename], check=True)
                elif language == "java":
                    class_name = kw_metadata['keyword']
                    subprocess.run(["javac", temp_filename], check=True)
                    subprocess.run(["java", "-cp", os.path.dirname(temp_filename), class_name], check=True)
                elif language == "cpp":
                    exe_filename = temp_filename.replace(".cpp", ".exe")
                    subprocess.run(["g++", temp_filename, "-o", exe_filename], check=True)
                    subprocess.run([exe_filename], check=True)
                elif language == "shell":
                    subprocess.run([r"C:\Program Files\Git\bin\bash.exe", temp_filename], check=True)

            except subprocess.CalledProcessError as e:
                print(f"Script failed with code {e.returncode}")
            except Exception as e:
                print(f"Execution failed: {str(e)}")
            finally:
                execution_queue.task_done()
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
                if language == "java":
                    class_file = temp_filename.replace(".java", ".class")
                    if os.path.exists(class_file):
                        os.remove(class_file)
                elif language in ("cpp", "csharp"):
                    exe_file = temp_filename.replace(f".{language}", ".exe")
                    if os.path.exists(exe_file):
                        os.remove(exe_file)

        except queue.Empty:
            continue

def voice_activated_recorder():
    porcupine = None
    audio_buffer = []
    is_recording = False
    start_time = None

    try:
        porcupine = pvporcupine.create(
            access_key=ACCESS_KEY,
            keyword_paths=KEYWORD_PATHS,
            sensitivities=[1, 1]
        )
        sample_rate = porcupine.sample_rate
        frame_length = porcupine.frame_length

        print("\nWake word activation ready.")

        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype='int16',
            blocksize=frame_length
        ) as stream:
            while not stop_event.is_set():
                audio_chunk, _ = stream.read(frame_length)
                if audio_chunk.size == 0:
                    continue

                audio_bytes = audio_chunk.tobytes()
                pcm = struct.unpack_from(f"{frame_length}h", audio_bytes)
                keyword_index = porcupine.process(pcm)

                if keyword_index == 0 and not is_recording:
                    is_recording = True
                    audio_buffer.append(audio_chunk)
                    start_time = time.time()
                    print("Recording started")

                elif keyword_index == 1 and is_recording:
                    is_recording = False
                    audio_buffer.append(audio_chunk)
                    if audio_buffer:
                        audio_data = np.concatenate(audio_buffer)
                        timestamp = int(time.time())
                        filename = f"voice_{timestamp}.wav"
                        wavfile.write(filename, sample_rate, audio_data)
                        audio_queue.put(filename)
                        print(f"Saved {len(audio_data) / sample_rate:.1f}s audio")
                        audio_buffer.clear()
                    start_time = None
                    print("Recording stopped")

                elif is_recording:
                    if time.time() - start_time > MAX_RECORDING_DURATION:
                        is_recording = False
                        if audio_buffer:
                            audio_data = np.concatenate(audio_buffer)
                            timestamp = int(time.time())
                            filename = f"voice_{timestamp}.wav"
                            wavfile.write(filename, sample_rate, audio_data)
                            audio_queue.put(filename)
                            print(f"Saved (timeout) {len(audio_data) / sample_rate:.1f}s audio")
                            audio_buffer.clear()
                        start_time = None
                        print("Recording stopped due to timeout")
                    else:
                        audio_buffer.append(audio_chunk)

    except Exception as e:
        print("\nRecording error:")
        traceback.print_exc()
        stop_event.set()
    finally:
        if porcupine is not None:
            porcupine.delete()

if __name__ == "__main__":
    from multiprocessing import freeze_support

    freeze_support()

    execution_queue = Manager().Queue()

    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"Using GPU: {torch.cuda.get_device_name(0)}")

    processor = threading.Thread(target=process_audio, daemon=True)
    processor.start()

    executor = Process(target=execute_scripts, args=(execution_queue,), daemon=True)
    executor.start()

    try:
        voice_activated_recorder()
    except KeyboardInterrupt:
        print("\nShutting down...")
        stop_event.set()

        while not audio_queue.empty() or not execution_queue.empty():
            time.sleep(0.1)

        while not audio_queue.empty():
            try:
                filename = audio_queue.get_nowait()
                if os.path.exists(filename):
                    os.remove(filename)
            except queue.Empty:
                break

        if executor.is_alive():
            executor.terminate()
            executor.join()

        print("System shutdown complete")
