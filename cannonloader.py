import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
from typing import Dict, List, Tuple
import struct
import redcon_webp_extractor as webpex
import redcon_ogg_extractor as oggex
from PIL import Image, ImageTk
import pygame
import threading
import io
from pydub import AudioSegment
import tempfile
import atexit

class GameModdingTool:
    def __init__(self, root):
        self.root = root
        self.root.title("CannonLoader V0.0.1 - Audio / Texture pack loader")
        self.root.geometry("1200x800")
        icon_path = "icon.jpg"
        icon_load = Image.open(icon_path)
        icon_render = ImageTk.PhotoImage(icon_load)
        root.iconphoto(False, icon_render)
        root.iconbitmap("icon.ico") 

        # Initialize pygame mixer for audio playback (deferred init allowed)
        try:
            pygame.mixer.init()
            self.audio_enabled = True
        except Exception:
            self.audio_enabled = False

        # Check for pydub + ffmpeg availability for audio conversion
        try:
            AudioSegment.silent(duration=1)
            self.audio_conversion_enabled = True
        except Exception:
            self.audio_conversion_enabled = False

        # Data storage
        self.current_file = None
        self.extracted_files: Dict[str, dict] = {}  # filename -> { offset, size, data, original_data, file_path?, file_type }
        self.file_type = None  # 'webp' for tx.pk (images) or 'ogg' for audio pk
        self.extraction_output_path = None
        self.current_audio_tempfile = None  # path to temp file used for playback
        self.current_image_tk = None  # keep reference to PhotoImage
        self.playback_lock = threading.Lock()

        # New option: store extracted in memory
        self.store_in_memory_var = tk.BooleanVar(value=True)

        self.setup_ui()
        atexit.register(self._cleanup_on_exit)

    def setup_ui(self):
        # Main frame with paned window for resizable sections
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left panel for controls and file list
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)

        # Right panel for preview
        right_frame = ttk.LabelFrame(main_paned, text="Preview", padding="5")
        main_paned.add(right_frame, weight=1)

        left_frame.columnconfigure(0, weight=1)

        # File selection section
        file_frame = ttk.LabelFrame(left_frame, text="File Selection", padding="5")
        file_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        file_frame.columnconfigure(1, weight=1)

        ttk.Button(file_frame, text="Select .pk File", command=self.select_file).grid(row=0, column=0, padx=(0, 10))
        self.file_path_var = tk.StringVar(value="No file selected")
        ttk.Label(file_frame, textvariable=self.file_path_var).grid(row=0, column=1, sticky=(tk.W, tk.E))

        # Extraction section
        extract_frame = ttk.LabelFrame(left_frame, text="Extraction", padding="5")
        extract_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        extract_frame.columnconfigure(2, weight=1)

        ttk.Button(extract_frame, text="Select Output Folder (Not required)", command=self.select_output_folder).grid(row=0, column=0, padx=(0, 10))
        self.extract_button = ttk.Button(extract_frame, text="Extract Files", command=self.extract_files, state="disabled")
        self.extract_button.grid(row=0, column=1, padx=(0, 10))
        self.store_mem_check = ttk.Checkbutton(extract_frame, text="Store extracted in memory", variable=self.store_in_memory_var)
        self.store_mem_check.grid(row=0, column=2, padx=(10, 0))

        self.output_path_var = tk.StringVar(value="No output folder selected")
        ttk.Label(extract_frame, textvariable=self.output_path_var).grid(row=1, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(6,0))

        # File list section
        list_frame = ttk.LabelFrame(left_frame, text="Extracted Files", padding="5")
        list_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.file_tree = ttk.Treeview(list_frame, columns=('Size', 'Type', 'Status'), show='tree headings')
        self.file_tree.heading('#0', text='Filename')
        self.file_tree.column('#0', width=260)
        self.file_tree.heading('Size', text='Size (bytes)')
        self.file_tree.column('Size', width=100, anchor='center')
        self.file_tree.heading('Type', text='Type')
        self.file_tree.column('Type', width=80, anchor='center')
        self.file_tree.heading('Status', text='Status')
        self.file_tree.column('Status', width=120, anchor='center')
        self.file_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.file_tree.bind('<<TreeviewSelect>>', self.on_file_select)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.file_tree.yview)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.file_tree.configure(yscrollcommand=scrollbar.set)

        # Replacement
        replace_frame = ttk.LabelFrame(left_frame, text="File Replacement", padding="5")
        replace_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        replace_frame.columnconfigure(2, weight=1)

        self.replace_button = ttk.Button(replace_frame, text="Replace Selected File", command=self.replace_file, state="disabled")
        self.replace_button.grid(row=0, column=0, padx=(0, 10))

        self.auto_convert_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(replace_frame, text="Auto-convert formats", variable=self.auto_convert_var).grid(row=0, column=1, padx=(0, 10))

        self.save_modified_button = ttk.Button(replace_frame, text="Save Modified .pk File", command=self.save_modified_file, state="disabled")
        self.save_modified_button.grid(row=0, column=2)

        # Log
        log_frame = ttk.LabelFrame(left_frame, text="Log", padding="5")
        log_frame.grid(row=4, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, width=50)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        left_frame.rowconfigure(2, weight=1)
        left_frame.rowconfigure(4, weight=1)

        self.setup_preview_panel(right_frame)

    def setup_preview_panel(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        control_frame = ttk.Frame(parent)
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        control_frame.columnconfigure(1, weight=1)

        self.preview_type_var = tk.StringVar(value="No file selected")
        ttk.Label(control_frame, textvariable=self.preview_type_var, font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky=tk.W)

        self.audio_controls = ttk.Frame(control_frame)
        self.audio_controls.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(5, 0))

        ttk.Button(self.audio_controls, text="▶ Play", command=self.play_audio).grid(row=0, column=0, padx=(0, 5))
        ttk.Button(self.audio_controls, text="⏹ Stop", command=self.stop_audio).grid(row=0, column=1, padx=(0, 5))

        self.volume_var = tk.DoubleVar(value=0.7)
        ttk.Label(self.audio_controls, text="Volume:").grid(row=0, column=2, padx=(10, 5))
        volume_scale = ttk.Scale(self.audio_controls, from_=0.0, to=1.0, variable=self.volume_var, command=self.on_volume_change, length=100)
        volume_scale.grid(row=0, column=3, padx=(0, 5))
        self.audio_controls.grid_remove()

        self.preview_frame = ttk.Frame(parent, relief=tk.SUNKEN, borderwidth=2)
        self.preview_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        self.preview_frame.columnconfigure(0, weight=1)
        self.preview_frame.rowconfigure(0, weight=1)

        self.image_label = ttk.Label(self.preview_frame, text="Select a file to preview", anchor=tk.CENTER)
        self.image_label.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        info_frame = ttk.LabelFrame(parent, text="File Information", padding="5")
        info_frame.grid(row=2, column=0, sticky=(tk.W, tk.E))
        self.info_text = tk.Text(info_frame, height=4, width=40, wrap=tk.WORD, state=tk.DISABLED)
        self.info_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        info_scrollbar = ttk.Scrollbar(info_frame, orient="vertical", command=self.info_text.yview)
        info_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.info_text.configure(yscrollcommand=info_scrollbar.set)

        conversion_info_frame = ttk.Frame(parent)
        conversion_info_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        ttk.Button(conversion_info_frame, text="Conversion Info", command=self.show_conversion_info).grid(row=0, column=0)
        ttk.Button(conversion_info_frame, text="Clear Preview", command=self.clear_preview).grid(row=0, column=1, padx=(10, 0))

    def log_message(self, message: str):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def select_file(self):
        file_path = filedialog.askopenfilename(title="Select .pk file", filetypes=[("PK files", "*.pk"), ("All files", "*.*")])
        if file_path:
            self.current_file = file_path
            self.file_path_var.set(os.path.basename(file_path))
            self.extract_button.config(state="normal")
            self.log_message(f"Selected file: {file_path}")

            if file_path.lower().endswith('tx.pk'):
                self.file_type = "webp"
                self.log_message("Detected WebP image file (tx.pk)")
            elif file_path.lower().endswith('.pk'):
                self.file_type = "ogg"
                self.log_message("Detected OGG audio file (.pk)")
            else:
                self.file_type = "unknown"
                self.log_message("Unknown file type - will attempt OGG extraction")

    def select_output_folder(self):
        output_path = filedialog.askdirectory(title="Select output folder for extracted files")
        if output_path:
            self.extraction_output_path = output_path
            self.output_path_var.set(os.path.basename(output_path))
            self.log_message(f"Selected output folder: {output_path}")
            if self.current_file:
                self.extract_button.config(state="normal")

    def load_extracted_files(self):
        """(Legacy) load files from disk output folder into GUI"""
        if not self.extraction_output_path or not os.path.exists(self.extraction_output_path):
            return
        self.extracted_files.clear()
        for item in self.file_tree.get_children():
            self.file_tree.delete(item)
        try:
            for filename in os.listdir(self.extraction_output_path):
                file_path = os.path.join(self.extraction_output_path, filename)
                if os.path.isfile(file_path):
                    file_size = os.path.getsize(file_path)
                    with open(file_path, 'rb') as f:
                        file_data = f.read()
                    file_ext = os.path.splitext(filename)[1].lower()
                    if file_ext in ['.webp', '.png', '.jpg', '.jpeg', '.bmp', '.gif']:
                        file_type = 'Image'
                    elif file_ext in ['.ogg', '.wav', '.mp3', '.m4a', '.flac']:
                        file_type = 'Audio'
                    else:
                        file_type = 'Unknown'
                    self.extracted_files[filename] = {
                        'offset': -1,
                        'size': file_size,
                        'data': file_data,
                        'original_data': bytes(file_data),
                        'file_path': file_path,
                        'file_type': file_type
                    }
                    self.file_tree.insert('', 'end', text=filename, values=(file_size, file_type, "Extracted"))
                    self.log_message(f"Loaded: {filename} ({file_size} bytes)")
            if self.extracted_files:
                self.replace_button.config(state="normal")
                self.log_message(f"Loaded {len(self.extracted_files)} extracted files from output directory")
        except Exception as e:
            self.log_message(f"Error loading extracted files: {str(e)}")

    # ---------- NEW: in-memory extraction helpers ----------
    def _find_webp_entries(self, data: bytes) -> List[Tuple[int, int]]:
        """Return list of (offset, size) for WebP RIFF blocks"""
        results = []
        offset = 0
        length = len(data)
        while True:
            idx = data.find(b'RIFF', offset)
            if idx == -1:
                break
            # check for "WEBP" at idx+8
            if idx + 12 <= length and data[idx+8:idx+12] == b'WEBP':
                try:
                    chunk_size = struct.unpack_from('<I', data, idx+4)[0]
                    full_size = chunk_size + 8
                except Exception:
                    full_size = length - idx
                if idx + full_size > length:
                    full_size = length - idx
                results.append((idx, full_size))
                offset = idx + full_size
            else:
                offset = idx + 4
        return results

    def _find_ogg_entries(self, data: bytes) -> List[Tuple[int, int]]:
        """Return list of (offset, size) for complete Ogg streams by parsing pages."""
        results = []
        ogg_signature = b"OggS"
        cursor = 0
        length = len(data)

        while cursor < length:
            start = data.find(ogg_signature, cursor)
            if start == -1:
                break

            pos = start
            while pos < length:
            # Minimum Ogg page header size
                if pos + 27 > length:
                   break

                header_type_flag = data[pos + 5]
                segment_count = data[pos + 26]

            # Segment table
                seg_table_end = pos + 27 + segment_count
                if seg_table_end > length:
                    break

                segment_sizes = data[pos + 27:seg_table_end]
                page_data_size = sum(segment_sizes)
                page_full_size = 27 + segment_count + page_data_size

                end = pos + page_full_size
                if end > length:
                    break

                pos = end

            # End-of-stream page (0x04 flag)
                if header_type_flag & 0x04:
                    break

                # Must start next page with "OggS"
                if data.find(ogg_signature, pos) != pos:
                    break

            # Record complete file if we parsed at least one page
            if pos > start:
                results.append((start, pos - start))
                cursor = pos
            else:
                cursor = start + 4  # avoid infinite loop if bad data

        return results


    def extract_files_in_memory(self):
        """Extract assets by scanning the .pk and store them in memory with offsets."""
        if not self.current_file:
            messagebox.showwarning("Missing PK", "Please select a .pk file first.")
            return
        try:
            with open(self.current_file, 'rb') as f:
                pk_data = f.read()
            entries = []
            if self.file_type == 'webp':
                webps = self._find_webp_entries(pk_data)
                for off, sz in webps:
                    entries.append((off, sz, 'Image'))
            elif self.file_type == 'ogg':
                oggs = self._find_ogg_entries(pk_data)
                for off, sz in oggs:
                    entries.append((off, sz, 'Audio'))
            else:
                # if unknown, try both and merge (sorted)
                webps = [(o, s, 'Image') for o, s in self._find_webp_entries(pk_data)]
                oggs = [(o, s, 'Audio') for o, s in self._find_ogg_entries(pk_data)]
                entries = sorted(webps + oggs, key=lambda x: x[0])

            # Deduplicate / avoid overlaps (simple scan)
            cleaned = []
            last_end = -1
            for off, sz, ftype in entries:
                if off <= last_end:
                    continue
                cleaned.append((off, sz, ftype))
                last_end = off + sz - 1

            # Populate extracted_files
            self.extracted_files.clear()
            for i, (off, sz, ftype) in enumerate(cleaned):
                ext = '.webp' if ftype == 'Image' else '.ogg'
                filename = f"{ftype.lower()}_{i:04d}{ext}"
                data = pk_data[off: off + sz]
                self.extracted_files[filename] = {
                    'offset': off,
                    'size': sz,
                    'data': data,
                    'original_data': bytes(data),
                    'file_type': ftype,
                    # no file_path since it's in-memory
                }
            # Update treeview
            for item in self.file_tree.get_children():
                self.file_tree.delete(item)
            for name, info in self.extracted_files.items():
                self.file_tree.insert('', 'end', text=name, values=(info['size'], info['file_type'], "In-memory"))

            if self.extracted_files:
                self.replace_button.config(state="normal")
                self.save_modified_button.config(state="normal")
            self.log_message(f"In-memory extraction complete: {len(self.extracted_files)} assets found")
        except Exception as e:
            self.log_message(f"Error extracting in memory: {e}")
            messagebox.showerror("Extraction Error", f"Could not extract in memory: {e}")

    # ---------- end new helpers ----------

    def extract_files(self):
        """Extract files using existing modules OR the in-memory scanner depending on option"""
        if not self.current_file:
            messagebox.showwarning("Missing Selection", "Please select a .pk file first.")
            return
        if self.store_in_memory_var.get():
            self.log_message("Extracting files into memory (no disk write)...")
            self.extract_files_in_memory()
            return

        # fallback: run your provided extractor modules which save to disk
        if not self.extraction_output_path:
            messagebox.showwarning("Missing Output", "Please select an output folder for extracted files.")
            return
        try:
            self.log_message(f"Starting extraction of: {self.current_file}")
            self.log_message(f"Output directory: {self.extraction_output_path}")

            if self.file_type == "webp":
                self.log_message("Extracting WebP images using redcon_webp_extractor...")
                webpex.extract_webp_images(self.current_file, self.extraction_output_path)
                self.log_message("WebP extraction completed!")
            elif self.file_type == "ogg":
                self.log_message("Extracting OGG audio files using redcon_ogg_extractor...")
                oggex.extract_ogg_files(self.current_file, self.extraction_output_path)
                self.log_message("OGG extraction completed!")
            # Load the extracted files into GUI (legacy on-disk mode)
            self.load_extracted_files()
            if self.extracted_files:
                messagebox.showinfo("Extraction Complete", f"Successfully extracted {len(self.extracted_files)} files to:\n{self.extraction_output_path}")
            else:
                messagebox.showwarning("No Files", "No files were extracted. Check the log for details.")
        except Exception as e:
            error_msg = f"Error during extraction: {str(e)}"
            messagebox.showerror("Extraction Error", error_msg)
            self.log_message(error_msg)

    def save_extracted_files(self):
        """Files are already saved by the extraction modules (legacy)"""
        if not self.extracted_files:
            messagebox.showinfo("Info", "No files to save. Please extract files first.")
            return
        messagebox.showinfo("Files Already Saved", f"Files have already been extracted to:\n{self.extraction_output_path}")
        self.log_message("Files are already saved in the selected output directory")

    def replace_file(self):
        selection = self.file_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a file to replace.")
            return
        selected_item = selection[0]
        filename = self.file_tree.item(selected_item, 'text')
        if filename not in self.extracted_files:
            messagebox.showerror("Error", "Selected file not found in extracted files.")
            return

        new_file_path = filedialog.askopenfilename(title=f"Select replacement file for {filename}", filetypes=[("All files", "*.*")])
        if not new_file_path:
            return

        converted_path = None
        try:
            should_convert = self.auto_convert_var.get()
            original_file_type = self.extracted_files[filename]['file_type']

            if should_convert:
                converted_path = self.auto_convert_file(new_file_path, original_file_type, filename)
                if converted_path:
                    new_file_path = converted_path
                    self.log_message(f"Auto-converted file for compatibility")

            with open(new_file_path, 'rb') as f:
                new_data = f.read()

            # Update in-memory info
            old_size = self.extracted_files[filename]['size']
            self.extracted_files[filename]['data'] = new_data
            self.extracted_files[filename]['size'] = len(new_data)

            # If file exists on-disk (legacy extraction), update that too
            if 'file_path' in self.extracted_files[filename]:
                try:
                    with open(self.extracted_files[filename]['file_path'], 'wb') as f:
                        f.write(new_data)
                except Exception:
                    pass

            self.file_tree.item(selected_item, values=(len(new_data), self.extracted_files[filename]['file_type'], "Modified"))
            self.log_message(f"Replaced {filename} with {os.path.basename(new_file_path)}")
            self.log_message(f"Size changed from {old_size} to {len(new_data)} bytes")

            self.save_modified_button.config(state="normal")
            if len(new_data) != old_size:
                messagebox.showwarning("Size Mismatch", f"Warning: New file size ({len(new_data)} bytes) differs from original ({old_size} bytes).\nThis may cause issues with the game. Consider resizing the file to match the original.")
            # Refresh preview if the replaced file is selected
            cursel = self.file_tree.selection()
            if cursel and self.file_tree.item(cursel[0], 'text') == filename:
                self.on_file_select(None)

        except Exception as e:
            messagebox.showerror("Replacement Error", f"Error replacing file: {str(e)}")
            self.log_message(f"Replacement error: {str(e)}")
        finally:
            if converted_path and converted_path != new_file_path:
                try:
                    os.unlink(converted_path)
                except Exception:
                    pass

    def auto_convert_file(self, file_path: str, target_type: str, original_filename: str) -> str:
        file_ext = os.path.splitext(file_path)[1].lower()
        try:
            if target_type == 'Image':
                if file_ext not in ['.webp']:
                    return self.convert_image_to_webp(file_path, original_filename)
            elif target_type == 'Audio':
                if file_ext not in ['.ogg']:
                    return self.convert_audio_to_ogg(file_path, original_filename)
        except Exception as e:
            self.log_message(f"Auto-conversion failed: {str(e)}")
            messagebox.showwarning("Conversion Failed", f"Could not auto-convert file. Using original format.\nError: {str(e)}")
        return None

    def convert_image_to_webp(self, input_path: str, original_filename: str) -> str:
        try:
            with Image.open(input_path) as img:
                temp_dir = tempfile.gettempdir()
                base_name = os.path.splitext(original_filename)[0]
                webp_path = os.path.join(temp_dir, f"{base_name}_converted.webp")
                if img.mode in ['RGBA', 'LA']:
                    img.save(webp_path, 'WEBP', lossless=True, quality=95)
                else:
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    img.save(webp_path, 'WEBP', quality=95)
                self.log_message(f"Converted {os.path.basename(input_path)} to WebP format")
                return webp_path
        except Exception as e:
            raise Exception(f"Image conversion failed: {str(e)}")

    def convert_audio_to_ogg(self, input_path: str, original_filename: str) -> str:
        if not self.audio_conversion_enabled:
            raise Exception("Audio conversion not available (pydub/ffmpeg not available)")
        try:
            audio = AudioSegment.from_file(input_path)
            temp_dir = tempfile.gettempdir()
            base_name = os.path.splitext(original_filename)[0]
            ogg_path = os.path.join(temp_dir, f"{base_name}_converted.ogg")
            audio.export(ogg_path, format="ogg", codec="libvorbis")
            self.log_message(f"Converted {os.path.basename(input_path)} to OGG format")
            return ogg_path
        except Exception as e:
            raise Exception(f"Audio conversion failed: {str(e)}")

    def get_conversion_info(self) -> str:
        info = "Auto-conversion capabilities:\n"
        info += "• Images: PNG, JPG, BMP, GIF → WebP ✓\n"
        if self.audio_conversion_enabled:
            info += "• Audio: MP3, WAV, M4A, etc. → OGG ✓\n"
        else:
            info += "• Audio conversion: Not available (install pydub and ffmpeg)\n"
        return info

    def find_file_offsets_in_pk(self, pk_data: bytes, target_file_data: bytes) -> int:
        for i in range(len(pk_data) - len(target_file_data) + 1):
            if pk_data[i:i + len(target_file_data)] == target_file_data:
                return i
        return -1

    def save_modified_file(self):
        if not self.current_file or not self.extracted_files:
            messagebox.showwarning("Nothing to Save", "No modifications to save.")
            return

        save_path = filedialog.asksaveasfilename(title="Save modified .pk file", defaultextension=".pk", filetypes=[("PK files", "*.pk"), ("All files", "*.*")])
        if not save_path:
            return

        def save_worker():
            try:
                self.log_message("Creating modified .pk file...")
                self.root.update_idletasks()

                # Read original PK file as a mutable bytearray
                with open(self.current_file, 'rb') as f:
                    original_data = bytearray(f.read())

                self.log_message(f"Loaded original file: {len(original_data)} bytes")
                self.root.update_idletasks()

                modifications_made = 0
                total_files = len([f for f in self.extracted_files.values() if f['original_data'] != f['data']])
                processed = 0

                for filename, file_info in self.extracted_files.items():
                    original_file_data = file_info['original_data']
                    new_file_data = file_info['data']
                    if original_file_data == new_file_data:
                        continue

                    processed += 1
                    self.log_message(f"Processing {filename} ({processed}/{total_files})...")
                    self.root.update_idletasks()

                    # Prefer stored offset if present
                    offset = file_info.get('offset', None)
                    if offset is not None and offset >= 0:
                        # Validate that the original data matches the pk at that offset
                        if original_data[offset:offset + len(original_file_data)] != original_file_data:
                            # mismatch - fallback to searching
                            offset = self.find_file_offsets_in_pk(original_data, original_file_data)
                    else:
                        offset = self.find_file_offsets_in_pk(original_data, original_file_data)

                    if offset != -1 and offset is not None:
                        original_size = len(original_file_data)
                        new_size = len(new_file_data)

                        if new_size <= original_size:
                            original_data[offset:offset + new_size] = new_file_data
                            if new_size < original_size:
                                original_data[offset + new_size:offset + original_size] = b'\x00' * (original_size - new_size)
                            modifications_made += 1
                            self.log_message(f"✓ Replaced {filename} at offset 0x{offset:08X}")
                        else:
                            original_data[offset:offset + original_size] = new_file_data[:original_size]
                            modifications_made += 1
                            self.log_message(f"⚠ Replaced {filename} (truncated from {new_size} to {original_size} bytes)")
                    else:
                        self.log_message(f"✗ Could not locate {filename} in original .pk file")

                    self.root.update_idletasks()

                if modifications_made == 0:
                    self.root.after(0, lambda: messagebox.showinfo("No Changes", "No modifications were found to save."))
                    return

                self.log_message("Writing modified .pk file...")
                self.root.update_idletasks()

                with open(save_path, 'wb') as f:
                    f.write(original_data)

                self.root.after(0, lambda: messagebox.showinfo("Success", f"Modified .pk file saved successfully!\nFile: {save_path}\nModifications applied: {modifications_made}"))
                self.log_message(f"✓ Modified .pk file saved: {save_path}")
                self.log_message(f"Total modifications applied: {modifications_made}")

            except Exception as e:
                error_msg = f"Error saving modified file: {str(e)}"
                self.root.after(0, lambda: messagebox.showerror("Save Error", error_msg))
                self.log_message(f"✗ {error_msg}")

        thread = threading.Thread(target=save_worker, daemon=True)
        thread.start()

    def on_file_select(self, event):
        selection = self.file_tree.selection()
        if not selection:
            self.clear_preview()
            return
        selected_item = selection[0]
        filename = self.file_tree.item(selected_item, 'text')
        if filename not in self.extracted_files:
            self.clear_preview()
            return

        file_info = self.extracted_files[filename]
        file_type = file_info.get('file_type', 'Unknown')
        file_size = file_info.get('size', 0)

        self.info_text.configure(state=tk.NORMAL)
        self.info_text.delete('1.0', tk.END)
        self.info_text.insert(tk.END, f"Filename: {filename}\nType: {file_type}\nSize: {file_size} bytes\n")
        self.info_text.configure(state=tk.DISABLED)

        # stop playback
        self.stop_audio()

        if file_type == 'Image':
            try:
                data = file_info['data']
                img = Image.open(io.BytesIO(data))
                max_w, max_h = 800, 600
                img.thumbnail((max_w, max_h), Image.LANCZOS)
                self.current_image_tk = ImageTk.PhotoImage(img)
                self.image_label.configure(image=self.current_image_tk, text="")
                self.preview_type_var.set("Image Preview")
                self.audio_controls.grid_remove()
            except Exception as e:
                self.image_label.configure(image='', text=f"Could not preview image:\n{e}")
                self.preview_type_var.set("Image Preview (error)")
                self.audio_controls.grid_remove()
        elif file_type == 'Audio':
            try:
                fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(filename)[1] or '.ogg')
                os.close(fd)
                with open(tmp_path, 'wb') as tf:
                    tf.write(file_info['data'])
                self.current_audio_tempfile = tmp_path
                self.preview_type_var.set("Audio Preview")
                self.image_label.configure(image='', text=f"Audio: {filename}\nSize: {file_size} bytes")
                self.audio_controls.grid()
                try:
                    pygame.mixer.music.set_volume(self.volume_var.get())
                except Exception:
                    pass
            except Exception as e:
                self.image_label.configure(image='', text=f"Could not prepare audio preview:\n{e}")
                self.preview_type_var.set("Audio Preview (error)")
                self.audio_controls.grid_remove()
        else:
            try:
                display = file_info['data'][:256]
                hexview = ' '.join(f"{b:02X}" for b in display)
                self.image_label.configure(image='', text=f"Unknown file type\nHex header:\n{hexview}")
                self.preview_type_var.set("Unknown Preview")
                self.audio_controls.grid_remove()
            except Exception as e:
                self.image_label.configure(image='', text="Could not preview file")
                self.preview_type_var.set("Unknown Preview")
                self.audio_controls.grid_remove()

    def play_audio(self):
        if not self.audio_enabled:
            messagebox.showwarning("Audio disabled", "Audio playback not available (pygame mixer failed).")
            return
        if not self.current_audio_tempfile or not os.path.exists(self.current_audio_tempfile):
            messagebox.showwarning("No audio", "No audio selected for playback.")
            return
        with self.playback_lock:
            try:
                try:
                    pygame.mixer.music.stop()
                except Exception:
                    pass
                pygame.mixer.music.load(self.current_audio_tempfile)
                pygame.mixer.music.set_volume(self.volume_var.get())
                pygame.mixer.music.play(loops=0)
                self.log_message(f"Playing audio: {os.path.basename(self.current_audio_tempfile)}")
            except Exception as e:
                messagebox.showerror("Playback Error", f"Could not play audio: {e}")
                self.log_message(f"Playback error: {e}")

    def stop_audio(self):
        with self.playback_lock:
            try:
                if self.audio_enabled:
                    try:
                        pygame.mixer.music.stop()
                    except Exception:
                        pass
            finally:
                if self.current_audio_tempfile:
                    try:
                        os.unlink(self.current_audio_tempfile)
                    except Exception:
                        pass
                    self.current_audio_tempfile = None

    def on_volume_change(self, val):
        try:
            v = float(val)
            if self.audio_enabled:
                try:
                    pygame.mixer.music.set_volume(v)
                except Exception:
                    pass
        except Exception:
            pass

    def show_conversion_info(self):
        info = self.get_conversion_info()
        messagebox.showinfo("Conversion Info", info)

    def clear_preview(self):
        self.stop_audio()
        self.image_label.configure(image='', text="Select a file to preview")
        self.info_text.configure(state=tk.NORMAL)
        self.info_text.delete('1.0', tk.END)
        self.info_text.configure(state=tk.DISABLED)
        self.preview_type_var.set("No file selected")
        self.audio_controls.grid_remove()
        self.current_image_tk = None

    def _cleanup_on_exit(self):
        try:
            self.stop_audio()
        except Exception:
            pass
        try:
            pygame.mixer.quit()
        except Exception:
            pass

if __name__ == "__main__":
    root = tk.Tk()
    try:
        app = GameModdingTool(root)
    except Exception as e:
        messagebox.showerror("Initialization Error", f"Failed to initialize application: {e}\nSee console for details.")
        raise
    try:
        root.update_idletasks()
        w = root.winfo_width(); h = root.winfo_height(); ws = root.winfo_screenwidth(); hs = root.winfo_screenheight()
        x = (ws // 2) - (w // 2); y = (hs // 2) - (h // 2)
        root.geometry(f"+{x}+{y}")
    except Exception:
        pass
    root.mainloop()
