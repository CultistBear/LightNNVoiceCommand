# **LightNNVoiceCommand**

An offline, energy-efficient voice-command recognition system built around a fine-tuned Whisper-small model and a Porcupine wake-word engine. 

---

## **Installation**

**Clone the repository**
```bash
git clone https://github.com/CultistBear/LightNNVoiceCommand.git
cd LightNNVoiceCommand
```

**Create and activate a Python virtual environment**
```bash
python3 -m venv env
source env/bin/activate
```

**Install dependencies**
```bash
pip install -r requirements.txt
```

## **Configuration**

**1. Download the ASR model**
#### Large files require Git LFS:
Linux
```bash
sudo apt-get install git-lfs
```
macOS
```bash
brew install git-lfs
```

Initialize and fetch the model:
```bash
git lfs install
git clone https://huggingface.co/CultistBear/Whisper-small-finetuned-space/
```

**2. Sign in and create your own Porcupine Wake-word and Shutdown model from https://picovoice.ai/platform/porcupine/ and download those models**

**3. Configure Porcupine keywords**
    In v4.py, set the absolute paths to the .ppn files:

```python
WAKE_KEYWORD_PATH     = r"/path/to/wake-word.ppn"
SHUTDOWN_KEYWORD_PATH = r"/path/to/shutdown-word.ppn"
```

**4. Set Porcupine access keys from your account**
In constants.py:

```python
MY_API_KEY_PORC       = "YOUR_PICOVOICE_ACCESS_KEY"
RISABH_API_KEY_PORC   = "YOUR_PICOVOICE_ACCESS_KEY"
```
(Note: You have to run each model with 1 api key, that is, wake word will take 1 api key and the shutdown word will take another, thats why we have provided 2 api keys in the code, but we had the enterprise plan so we could activate both the porcupine models with one account)</br>
Once activated, the system runs entirely offline.

**5. Set up the Whisper checkpoints file path in constants**
<pre>LATEST_TRAINED = r""</pre>

**6. Install and start MongoDB Community Edition**

macOS (Homebrew)
```bash
brew tap mongodb/brew
brew install mongodb-community@6.0
brew services start mongodb-community@6.0
```
Ubuntu / Debian
```bash
sudo apt-get update
sudo apt-get install -y mongodb
sudo systemctl start mongod
```
Windows
```
Download and install from https://www.mongodb.com/try/download/community
Ensure the MongoDB service is running.
```

**7. Verify MongoDB connection**
Confirm the server is accessible at mongodb://localhost:27017/, as used in app.py:

```python
client = MongoClient("mongodb://localhost:27017/")
```

## **Running the Web-App and Model**

**1. Start the Flask web-app**
```bash
python app.py
```
  Navigate to http://localhost:5000</br>
  Upload scripts and assign keywords via the UI.

**2. Launch the voice-command service**
```bash
python v4.py
```
  Porcupine listens for the wake word.</br>
  Upon detection, audio is recorded, transcribed by the Whisper model, and matching scripts execute.</br>

**3. Usage flow**

  Speak the wake word</br>
  Issue a multi-word command</br>
  Observe transcription and script execution in the console</br>

