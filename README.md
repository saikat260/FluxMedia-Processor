# PyMedia Obfuscator

![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Build Status](https://img.shields.io/badge/build-passing-brightgreen)
![FFmpeg](https://img.shields.io/badge/dependency-ffmpeg-orange)

**PyMedia Obfuscator** is a high-performance, GUI-based media processing utility designed for data scientists, QA engineers, and broadcast professionals. The tool facilitates the generation of mathematically unique media variations to facilitate robust machine learning model training, stress-testing of internal media delivery pipelines, and metadata anonymization for secure research environments.

By utilizing advanced temporal and spatial randomization techniques, PyMedia Obfuscator ensures that every output file possesses a unique digital signature (hash) while preserving the core visual and acoustic integrity of the source material.

---

## 🚀 Key Features

-   **Multi-threaded Processing:** Leverages concurrent execution for high-throughput batch processing of media libraries.
-   **Metadata Anonymization:** Complete stripping of EXIF, XMP, and other identifying metadata to ensure data privacy.
-   **Spatial & Temporal Randomization:** Automated application of randomized cropping, mirroring, and timeline adjustments (variable FPS and PTS).
-   **Visual Obfuscation:** Dynamic application of luma/chroma adjustments, grain injection, and vignette effects to simulate various capture environments.
-   **Acoustic Signature Transformation:** Sophisticated audio processing including pitch shifting, equalization, and ambient noise injection.
-   **Automated Delogo Pipeline:** Integrated capability to obfuscate or remove static screen elements (watermarks, logos) via coordinate-based masking.

---

## 🛠 Prerequisites

### FFmpeg Installation
PyMedia Obfuscator requires [FFmpeg](https://ffmpeg.org/) to be installed and accessible in your system's PATH.

#### **Windows**
1.  Download the latest "essentials" build from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/).
2.  Extract the ZIP file and move the folder to `C:\ffmpeg`.
3.  Add `C:\ffmpeg\bin` to your System Environment Variables (PATH).
4.  Verify: Run `ffmpeg -version` in Command Prompt.

#### **macOS**
1.  Install [Homebrew](https://brew.sh/).
2.  Run: `brew install ffmpeg`
3.  Verify: Run `ffmpeg -version` in Terminal.

#### **Linux (Ubuntu/Debian)**
1.  Run: `sudo apt update && sudo apt install ffmpeg`
2.  Verify: Run `ffmpeg -version` in Terminal.

---

## 📦 Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/yourusername/PyMedia-Obfuscator.git
    cd PyMedia-Obfuscator
    ```

2.  **Create a Virtual Environment:**
    ```bash
    python -m venv venv
    # Windows:
    .\venv\Scripts\activate
    # macOS/Linux:
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

---

## 📖 Usage Guide

Running the application:
```bash
python video_randomizer.py
```

### GUI Section Overview
1.  **Input/Output Configuration:** Select the source directory containing `.mp4` files and the destination for processed outputs.
2.  **Global Parameters:** Toggle mirroring and strict subtitle detection.
3.  **Delogo Coordinates:** 
    -   **X / Y:** The horizontal and vertical position of the logo (top-left corner).
    -   **W / H:** The width and height of the mask to be applied.
    -   *Note:* If these fields are left empty, no delogo filter will be applied.
4.  **Log Console:** Monitor real-time progress and FFmpeg exit codes during batch operations.

---

## 🔨 Compiling to Executable

To distribute PyMedia Obfuscator as a standalone Windows application, use `PyInstaller`:

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile video_randomizer.py
```

---

## ⚖️ Disclaimer

**PyMedia Obfuscator is intended for internal testing, educational, and authorized media manipulation purposes ONLY.** 

The developers do not condone or support the use of this tool for the unauthorized modification of copyrighted material or for bypassing digital security systems. Users are solely responsible for ensuring their use of the software complies with all applicable local, state, and international laws.

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for more information.
