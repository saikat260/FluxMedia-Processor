import os
import subprocess
import random
import uuid
import sys
import logging
import threading
import queue
import json
import re
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import customtkinter as ctk
from tkinter import filedialog, messagebox

# --- Configuration Handling ---

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {"ffmpeg_path": "ffmpeg", "ffprobe_path": "ffprobe"}

def save_config(ffmpeg_path, ffprobe_path):
    with open(CONFIG_FILE, 'w') as f:
        json.dump({"ffmpeg_path": ffmpeg_path, "ffprobe_path": ffprobe_path}, f)

# --- Logging Redirection ---

class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(self.format(record))

# --- Core Logic Class ---

class VideoRandomizer:
    def __init__(self, input_dir, output_dir, ffmpeg_path="ffmpeg", ffprobe_path="ffprobe", 
                 enable_mirror=True, strict_check=True, max_workers=2, 
                 progress_callback=None, file_status_callback=None, delogo_params=None):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self.enable_mirror = enable_mirror
        self.strict_check = strict_check
        self.max_workers = max_workers
        self.progress_callback = progress_callback
        self.file_status_callback = file_status_callback
        self.delogo_params = delogo_params
        
        self.processed_dir = self.output_dir / "randomized_output"
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def verify_paths(self):
        """Verify that the provided paths for FFmpeg/FFprobe are valid."""
        try:
            subprocess.run([self.ffmpeg_path, "-version"], capture_output=True, check=True)
            subprocess.run([self.ffprobe_path, "-version"], capture_output=True, check=True)
            return True
        except Exception:
            return False

    def get_video_info(self, file_path):
        cmd = [
            self.ffprobe_path, "-v", "error",
            "-show_entries", "format=duration:stream=index,codec_type",
            "-of", "csv=p=0",
            str(file_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        lines = result.stdout.strip().split('\n')
        
        duration = 0.0
        has_audio = False
        has_subtitles = False
        
        for line in lines:
            if not line: continue
            parts = line.split(',')
            if len(parts) == 1: # Duration from format
                try: duration = float(parts[0])
                except: pass
            elif 'audio' in line:
                has_audio = True
            elif 'subtitle' in line:
                has_subtitles = True
                
        return has_audio, has_subtitles, duration

    def generate_random_params(self):
        return {
            "hflip": self.enable_mirror and (random.random() < 0.5),
            "crop_w": random.randint(2, 4),
            "crop_h": random.randint(2, 4),
            "brightness": random.uniform(-0.02, 0.02),
            "contrast": random.uniform(0.98, 1.02),
            "saturation": random.uniform(0.95, 1.05),
            "gamma": random.uniform(0.98, 1.02),
            "speed": random.uniform(0.98, 1.02),
            "pitch_semitones": random.uniform(-0.5, 0.5),
            "noise_seed": random.randint(1, 1000000),
            "vignette_angle": random.uniform(0.05, 0.15),
            "fps": random.choice([23.976, 24, 25, 29.97, 30]),
            "noise_amplitude": random.uniform(0.0001, 0.0003),
            "eq_gain": random.uniform(-1.0, 1.0)
        }

    def build_filter_complex(self, params, has_audio):
        v_filters = []
        if self.delogo_params:
            d = self.delogo_params
            v_filters.append(f"delogo=x={d['x']}:y={d['y']}:w={d['w']}:h={d['h']}")
        if params["hflip"]: v_filters.append("hflip")
        v_filters.append(f"crop=iw-{params['crop_w']*2}:ih-{params['crop_h']*2}:{params['crop_w']}:{params['crop_h']}")
        v_filters.append(f"eq=brightness={params['brightness']}:contrast={params['contrast']}:saturation={params['saturation']}:gamma={params['gamma']}")
        v_filters.append(f"noise=all_seed={params['noise_seed']}:alls=1:allf=t")
        v_filters.append(f"vignette=angle={params['vignette_angle']}")
        v_filters.append(f"setpts={1.0/params['speed']}*PTS")
        
        filter_complex = f"[0:v]{','.join(v_filters)}[v_out]"
        maps = ["-map", "[v_out]"]
        
        if has_audio:
            p_f = 2**(params["pitch_semitones"] / 12)
            a_filters = [
                f"asetrate=44100*{p_f}", f"aresample=44100",
                f"atempo={1.0/p_f}", f"atempo={params['speed']}",
                f"equalizer=f=1000:width_type=h:width=200:g={params['eq_gain']}"
            ]
            filter_complex += f";[0:a]{','.join(a_filters)}[a_p];"
            filter_complex += f"anoisesrc=color=white:amplitude={params['noise_amplitude']}[back_noise];"
            filter_complex += f"[a_p][back_noise]amix=inputs=2:duration=first[a_out]"
            maps.extend(["-map", "[a_out]"])
            
        return filter_complex, maps

    def process_file(self, file_path):
        worker_id = threading.current_thread().name
        try:
            if self.file_status_callback:
                self.file_status_callback(worker_id, f"Analyzing: {file_path.name}", 0)

            has_audio, has_subtitles, duration = self.get_video_info(file_path)
            if has_subtitles:
                logging.warning(f"WARNING: {file_path.name} has subtitles.")
                    
            params = self.generate_random_params()
            f_c, maps = self.build_filter_complex(params, has_audio)
            
            output_path = self.processed_dir / f"rand_{uuid.uuid4().hex[:10]}.mp4"
            
            cmd = [self.ffmpeg_path, "-y", "-i", str(file_path), "-progress", "pipe:1", "-filter_complex", f_c] + maps + [
                "-c:v", "libx264", "-crf", "18", "-preset", "fast",
                "-r", str(params["fps"]), "-c:a", "aac", "-b:a", "192k",
                "-map_metadata", "-1", "-fflags", "+bitexact", str(output_path)
            ]
            
            if self.file_status_callback:
                self.file_status_callback(worker_id, f"Processing: {file_path.name}", 0)

            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, universal_newlines=True)
            
            time_pattern = re.compile(r"out_time_ms=(\d+)")
            
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                
                if line:
                    match = time_pattern.search(line)
                    if match and duration > 0:
                        current_ms = int(match.group(1))
                        progress = (current_ms / 1000000) / duration
                        if self.file_status_callback:
                            self.file_status_callback(worker_id, f"Processing: {file_path.name}", progress)

            if process.returncode != 0:
                raise subprocess.CalledProcessError(process.returncode, cmd)

            logging.info(f"Done: {file_path.name} -> {output_path.name}")
            if self.file_status_callback:
                self.file_status_callback(worker_id, f"Completed: {file_path.name}", 1.0)
            return True
        except Exception as e:
            logging.error(f"Failed {file_path.name}: {str(e)}")
            if self.file_status_callback:
                self.file_status_callback(worker_id, f"Failed: {file_path.name}", 0)
            return False

    def run(self):
        files = list(self.input_dir.glob("*.mp4"))
        if not files:
            logging.info("No MP4 files found.")
            return

        logging.info(f"Found {len(files)} files. Starting batch processing...")
        success = 0
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="Worker") as executor:
            # Map returns results in order, so we can track progress easily
            futures = [executor.submit(self.process_file, f) for f in files]
            for i, future in enumerate(futures):
                if future.result(): success += 1
                if self.progress_callback:
                    self.progress_callback((i + 1) / len(files))
        
        logging.info(f"Batch processing finished. Success: {success}/{len(files)}")

# --- GUI Application ---

class VideoRandomizerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("PyMedia Obfuscator")
        self.geometry("800x750")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.config = load_config()

        self.log_queue = queue.Queue()
        self.status_slots = {} # worker_name -> dict(label, progress)
        self._setup_logging()
        self._build_ui()
        self._check_logs()

    def _setup_logging(self):
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        handler = QueueHandler(self.log_queue)
        handler.setFormatter(logging.Formatter('%(asctime)s: %(message)s', '%H:%M:%S'))
        logger.addHandler(handler)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(7, weight=1) 

        # 1. Input Folder
        self.in_label = ctk.CTkLabel(self, text="Input Folder (Source MP4s):")
        self.in_label.grid(row=0, column=0, padx=20, pady=(20, 0), sticky="w")
        self.in_frame = self._create_path_row(row=1, placeholder="Select input folder...", command=self._browse_input)
        self.in_entry = self.in_frame.winfo_children()[0]

        # 2. Output Folder
        self.out_label = ctk.CTkLabel(self, text="Output Folder (Base Dir):")
        self.out_label.grid(row=2, column=0, padx=20, pady=(10, 0), sticky="w")
        self.out_frame = self._create_path_row(row=3, placeholder="Select output folder...", command=self._browse_output)
        self.out_entry = self.out_frame.winfo_children()[0]

        # 3. Dependency Settings
        self.dep_label = ctk.CTkLabel(self, text="Dependency Paths (Required if not in System PATH):")
        self.dep_label.grid(row=4, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.ffmpeg_frame = self._create_path_row(row=5, placeholder="Path to ffmpeg.exe", command=self._browse_ffmpeg)
        self.ffmpeg_entry = self.ffmpeg_frame.winfo_children()[0]
        self.ffmpeg_entry.insert(0, self.config.get("ffmpeg_path", "ffmpeg"))

        self.ffprobe_frame = self._create_path_row(row=6, placeholder="Path to ffprobe.exe", command=self._browse_ffprobe)
        self.ffprobe_entry = self.ffprobe_frame.winfo_children()[0]
        self.ffprobe_entry.insert(0, self.config.get("ffprobe_path", "ffprobe"))

        # 4. Filter Settings
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.grid(row=7, column=0, padx=20, pady=10, sticky="ew")
        
        self.mirror_check = ctk.CTkCheckBox(self.settings_frame, text="Enable Mirroring (50% Randomize)")
        self.mirror_check.select()
        self.mirror_check.grid(row=0, column=0, padx=20, pady=15)
        
        self.strict_check = ctk.CTkCheckBox(self.settings_frame, text="Strict Subtitle Warning")
        self.strict_check.select()
        self.strict_check.grid(row=0, column=1, padx=20, pady=15)

        # 4b. Delogo Settings
        self.delogo_frame = ctk.CTkFrame(self)
        self.delogo_frame.grid(row=8, column=0, padx=20, pady=5, sticky="ew")
        
        self.dl_label = ctk.CTkLabel(self.delogo_frame, text="Delogo Coordinates (Optional):", font=("Inter", 12, "bold"))
        self.dl_label.grid(row=0, column=0, columnspan=4, padx=10, pady=5, sticky="w")
        
        self.dl_x = self._create_labeled_entry(self.delogo_frame, "X:", 0, 1)
        self.dl_y = self._create_labeled_entry(self.delogo_frame, "Y:", 1, 1)
        self.dl_w = self._create_labeled_entry(self.delogo_frame, "W:", 2, 1)
        self.dl_h = self._create_labeled_entry(self.delogo_frame, "H:", 3, 1)

        # 5. Active Tasks
        self.active_tasks_label = ctk.CTkLabel(self, text="Active Tasks Processing:")
        self.active_tasks_label.grid(row=9, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.tasks_frame = ctk.CTkFrame(self)
        self.tasks_frame.grid(row=10, column=0, padx=20, pady=5, sticky="ew")
        
        # We will create slots based on max_workers (default 2)
        for i in range(2):
            w_name = f"Worker_{i}"
            f = ctk.CTkFrame(self.tasks_frame, fg_color="transparent")
            f.pack(fill="x", padx=10, pady=2)
            
            lbl = ctk.CTkLabel(f, text=f"Worker {i+1}: Idle", font=("Inter", 11))
            lbl.pack(side="left", padx=5)
            
            p = ctk.CTkProgressBar(f, width=200)
            p.pack(side="right", padx=5)
            p.set(0)
            
            self.status_slots[w_name] = {"label": lbl, "progress": p}

        # 6. Logs
        self.log_label = ctk.CTkLabel(self, text="Activity Logs:")
        self.log_label.grid(row=10, column=0, padx=20, pady=(10, 0), sticky="w")
        
        self.log_box = ctk.CTkTextbox(self, height=150)
        self.log_box.grid(row=11, column=0, padx=20, pady=10, sticky="nsew")
        self.log_box.configure(state="disabled")

        # 7. Controls
        self.bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.bottom_frame.grid(row=12, column=0, padx=20, pady=(10, 20), sticky="ew")
        self.bottom_frame.grid_columnconfigure(0, weight=1)

        self.progress_label = ctk.CTkLabel(self.bottom_frame, text="Overall Progress:")
        self.progress_label.grid(row=0, column=0, sticky="w", padx=(0, 10))

        self.progress = ctk.CTkProgressBar(self.bottom_frame)
        self.progress.grid(row=1, column=0, padx=(0, 10), sticky="ew")
        self.progress.set(0)
        
        self.start_btn = ctk.CTkButton(self.bottom_frame, text="Start Processing", command=self._start_thread, fg_color="#3498db", hover_color="#2980b9", height=40)
        self.start_btn.grid(row=0, column=1, rowspan=2)

    def _create_labeled_entry(self, parent, text, col, row_idx):
        lbl = ctk.CTkLabel(parent, text=text)
        lbl.grid(row=row_idx, column=col*2, padx=(10, 2), pady=5, sticky="e")
        ent = ctk.CTkEntry(parent, width=60)
        ent.grid(row=row_idx, column=col*2 + 1, padx=(2, 10), pady=5, sticky="w")
        return ent

    def _create_path_row(self, row, placeholder, command):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=0, padx=20, pady=(5, 10), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)
        
        entry = ctk.CTkEntry(frame, placeholder_text=placeholder)
        entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        btn = ctk.CTkButton(frame, text="Browse", width=100, command=command)
        btn.grid(row=0, column=1)
        return frame

    def _browse_input(self):
        d = filedialog.askdirectory()
        if d: self.in_entry.delete(0, "end"); self.in_entry.insert(0, d)

    def _browse_output(self):
        d = filedialog.askdirectory()
        if d: self.out_entry.delete(0, "end"); self.out_entry.insert(0, d)

    def _browse_ffmpeg(self):
        f = filedialog.askopenfilename(filetypes=[("Executables", "*.exe"), ("All files", "*.*")])
        if f: self.ffmpeg_entry.delete(0, "end"); self.ffmpeg_entry.insert(0, f); self._save_paths()

    def _browse_ffprobe(self):
        f = filedialog.askopenfilename(filetypes=[("Executables", "*.exe"), ("All files", "*.*")])
        if f: self.ffprobe_entry.delete(0, "end"); self.ffprobe_entry.insert(0, f); self._save_paths()

    def _save_paths(self):
        save_config(self.ffmpeg_entry.get(), self.ffprobe_entry.get())

    def _check_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(100, self._check_logs)

    def _update_progress(self, val):
        self.after(10, lambda: self.progress.set(val))

    def _update_file_status(self, worker_name, status_text, progress_val):
        def update():
            if worker_name in self.status_slots:
                slot = self.status_slots[worker_name]
                slot["label"].configure(text=status_text)
                slot["progress"].set(progress_val)
        self.after(10, update)

    def _start_thread(self):
        in_p, out_p = self.in_entry.get(), self.out_entry.get()
        ff_p, fp_p = self.ffmpeg_entry.get(), self.ffprobe_entry.get()
        
        if not in_p or not out_p:
            messagebox.showerror("Error", "Select input and output folders.")
            return

        # Collect Delogo params
        try:
            dl_p = None
            if self.dl_w.get() and self.dl_h.get():
                dl_p = {
                    "x": int(self.dl_x.get() or 0),
                    "y": int(self.dl_y.get() or 0),
                    "w": int(self.dl_w.get()),
                    "h": int(self.dl_h.get())
                }
        except ValueError:
            messagebox.showerror("Error", "Delogo coordinates must be integers.")
            return

        self.start_btn.configure(state="disabled")
        self.progress.set(0)
        
        threading.Thread(target=self._run_processing, args=(in_p, out_p, ff_p, fp_p, dl_p), daemon=True).start()

    def _run_processing(self, in_p, out_p, ff_p, fp_p, dl_p):
        try:
            randomizer = VideoRandomizer(
                in_p, out_p, ffmpeg_path=ff_p, ffprobe_path=fp_p,
                enable_mirror=self.mirror_check.get(),
                strict_check=self.strict_check.get(),
                progress_callback=self._update_progress,
                file_status_callback=self._update_file_status,
                delogo_params=dl_p
            )
            
            if not randomizer.verify_paths():
                logging.error("CRITICAL: FFmpeg or FFprobe invalid. Use Browse nodes to locate them.")
                return
                
            randomizer.run()
        except Exception as e:
            logging.error(f"Error: {str(e)}")
        finally:
            self.after(100, lambda: self.start_btn.configure(state="normal"))
            self.after(100, lambda: messagebox.showinfo("Done", "Complete!"))

if __name__ == "__main__":
    app = VideoRandomizerApp()
    app.mainloop()
