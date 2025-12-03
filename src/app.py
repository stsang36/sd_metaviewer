"""
Main application UI for SD MetaViewer.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
import os
from pathlib import Path
from typing import Optional, Dict, List

# Windows-specific imports (cached at module level)
try:
    import winreg
    _HAS_WINREG = True
except ImportError:
    _HAS_WINREG = False

# Enable DPI awareness for crisp display on high-res screens
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # Fallback for older Windows
    except Exception:
        pass

from .extractor import ImageMetadataExtractor
from .utils import create_app_icon, save_icon_file


def is_dark_mode() -> bool:
    """Detect if Windows is using dark mode."""
    if not _HAS_WINREG:
        return False
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return value == 0
    except Exception:
        return False


# Theme colors - defined once at module level for performance
THEMES = {
    'light': {
        'bg': '#f5f5f5',
        'bg_secondary': '#ffffff',
        'bg_tertiary': '#e8e8e8',
        'fg': '#1a1a1a',
        'fg_secondary': '#555555',
        'accent': '#0078d4',
        'accent_hover': '#106ebe',
        'border': '#d0d0d0',
        'text_border': '#c0c0c0',
        'text_bg': '#ffffff',
        'canvas_bg': '#e0e0e0',
        'tag_bg': '#e3f2fd',
        'tag_fg': '#1565c0',
        'tag_neg_bg': '#ffebee',
        'tag_neg_fg': '#c62828',
        'button_bg': '#e1e1e1',
        'button_active': '#c8c8c8',
        'button_border': '#b0b0b0',
    },
    'dark': {
        'bg': '#1e1e1e',
        'bg_secondary': '#252526',
        'bg_tertiary': '#2d2d30',
        'fg': '#e0e0e0',
        'fg_secondary': '#9d9d9d',
        'accent': '#0078d4',
        'accent_hover': '#1a8cff',
        'border': '#404040',
        'text_border': '#4a4a4a',
        'text_bg': '#252526',
        'canvas_bg': '#2d2d30',
        'tag_bg': '#264f78',
        'tag_fg': '#9cdcfe',
        'tag_neg_bg': '#4a2020',
        'tag_neg_fg': '#f48771',
        'button_bg': '#3c3c3c',
        'button_active': '#505050',
        'button_border': '#555555',
    }
}


class SDMetaViewer(tk.Tk):
    """Main application window."""
    
    def __init__(self):
        super().__init__()
        
        self.title("SD MetaViewer")
        
        # Detect theme early
        self.dark_mode = is_dark_mode()
        self.colors = THEMES['dark'] if self.dark_mode else THEMES['light']
        
        # Get screen dimensions and set appropriate window size
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        
        # Use 80% of screen size, but with reasonable limits
        win_width = min(max(1200, int(screen_width * 0.75)), 1600)
        win_height = min(max(800, int(screen_height * 0.8)), 1000)
        
        # Center the window
        x = (screen_width - win_width) // 2
        y = (screen_height - win_height) // 2 - 30  # Slightly above center
        
        self.geometry(f"{win_width}x{win_height}+{x}+{y}")
        self.minsize(1100, 700)  # Minimum size to show all UI elements
        
        # Set application icon (deferred to avoid slowdown)
        self._icon_photo = None
        self.after_idle(self._set_app_icon)
        
        # State - use __slots__ pattern mentally, minimal attributes
        self.current_image_path: Optional[str] = None
        self.current_metadata: Optional[Dict] = None
        self.image_history: List[str] = []
        self._is_navigating = False
        self.history_index = -1
        self.current_photo: Optional[ImageTk.PhotoImage] = None
        self.current_folder: Optional[str] = None
        self.folder_images: List[str] = []
        self.folder_index = -1
        self.recent_images: List[str] = []
        
        # Configure style with theme
        self._configure_theme()
        
        self._create_ui()
        self._setup_bindings()
        
        # Enable drag and drop (deferred)
        self.after_idle(self._setup_dnd)
        
        # Adjust layout after window is displayed
        self.after(50, self._adjust_initial_layout)
        
        # Start theme monitoring
        self._start_theme_monitor()
    
    def _start_theme_monitor(self):
        """Monitor for Windows theme changes."""
        self._check_theme_change()
    
    def _check_theme_change(self):
        """Check if system theme changed and update UI."""
        new_dark_mode = is_dark_mode()
        if new_dark_mode != self.dark_mode:
            self.dark_mode = new_dark_mode
            self.colors = THEMES['dark'] if self.dark_mode else THEMES['light']
            self._apply_theme()
        # Check again in 2 seconds (balance between responsiveness and CPU)
        self.after(2000, self._check_theme_change)
    
    def _apply_theme(self):
        """Apply current theme to all widgets."""
        c = self.colors
        
        # Update main window
        self.configure(bg=c['bg'])
        
        # Update ttk styles
        self._configure_theme()
        
        # Update tk widgets that don't use ttk styles
        self._update_widget_colors()
    
    def _update_widget_colors(self):
        """Update colors for tk widgets that don't use ttk styles."""
        c = self.colors
        
        # Text widgets
        text_widgets = [self.prompt_text, self.negative_text, self.params_text, 
                        self.raw_text, self.tags_text]
        for widget in text_widgets:
            widget.configure(
                bg=c['text_bg'], fg=c['fg'],
                insertbackground=c['fg'],
                highlightbackground=c['text_border'],
                selectbackground=c['accent']
            )
        
        # Update tags_text tag colors
        self.tags_text.tag_configure('tag', background=c['tag_bg'], foreground=c['tag_fg'])
        self.tags_text.tag_configure('tag_neg', background=c['tag_neg_bg'], foreground=c['tag_neg_fg'])
        self.tags_text.tag_configure('header', foreground=c['tag_fg'])
        self.tags_text.tag_configure('header_neg', foreground=c['tag_neg_fg'])
        
        # Canvas
        self.image_canvas.configure(bg=c['canvas_bg'])
        
        # Menus
        menu_config = {
            'bg': c['bg_secondary'], 'fg': c['fg'],
            'activebackground': c['accent'], 'activeforeground': 'white'
        }
        self.recent_menu.configure(**menu_config)
    
    def _configure_theme(self):
        """Configure ttk styles based on current theme."""
        c = self.colors
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Main backgrounds
        self.configure(bg=c['bg'])
        
        # Frame styles
        self.style.configure('TFrame', background=c['bg'])
        self.style.configure('Secondary.TFrame', background=c['bg_secondary'])
        
        # Label styles
        self.style.configure('TLabel', background=c['bg'], foreground=c['fg'], font=('Segoe UI', 10))
        self.style.configure('Header.TLabel', background=c['bg'], foreground=c['fg'], font=('Segoe UI', 12, 'bold'))
        self.style.configure('Title.TLabel', background=c['bg'], foreground=c['fg'], font=('Segoe UI', 14, 'bold'))
        self.style.configure('Secondary.TLabel', background=c['bg'], foreground=c['fg_secondary'], font=('Segoe UI', 10))
        
        # Button styles - modern rounded look
        self.style.configure('TButton',
            background=c['button_bg'],
            foreground=c['fg'],
            font=('Segoe UI', 10),
            borderwidth=1,
            relief='flat',
            focuscolor=c['accent'],
            padding=(14, 7)
        )
        self.style.map('TButton',
            background=[('active', c['button_active']), ('pressed', c['accent'])],
            foreground=[('pressed', '#ffffff')],
            relief=[('pressed', 'flat')]
        )
        # Configure button layout for rounder appearance
        self.style.layout('TButton', [
            ('Button.padding', {'sticky': 'nswe', 'children': [
                ('Button.label', {'sticky': 'nswe'})
            ]})
        ])
        
        # Accent button
        self.style.configure('Accent.TButton',
            background=c['accent'],
            foreground='#ffffff',
            font=('Segoe UI', 10, 'bold'),
            borderwidth=0,
            padding=(12, 6)
        )
        self.style.map('Accent.TButton',
            background=[('active', c['accent_hover']), ('pressed', c['accent_hover'])]
        )
        
        # Menubutton
        self.style.configure('TMenubutton',
            background=c['button_bg'],
            foreground=c['fg'],
            font=('Segoe UI', 10),
            borderwidth=0,
            padding=(12, 6)
        )
        self.style.map('TMenubutton',
            background=[('active', c['button_active']), ('pressed', c['accent'])],
            foreground=[('pressed', '#ffffff')]
        )

        # Notebook (tabs)
        self.style.configure('TNotebook', background=c['bg'], borderwidth=0)
        self.style.configure('TNotebook.Tab',
            background=c['bg_tertiary'],
            foreground=c['fg'],
            padding=(16, 8),
            font=('Segoe UI', 10)
        )
        self.style.map('TNotebook.Tab',
            background=[('selected', c['bg_secondary'])],
            foreground=[('selected', c['accent'])]
        )
        
        # PanedWindow
        self.style.configure('TPanedwindow', background=c['bg'])
        
        # Scrollbar - thin modern style
        self.style.configure('Vertical.TScrollbar',
            background=c['bg_tertiary'],
            troughcolor=c['bg_secondary'],
            borderwidth=0,
            arrowsize=0,
            width=10
        )
        self.style.map('Vertical.TScrollbar',
            background=[('active', c['fg_secondary'])]
        )
        
        # Separator
        self.style.configure('TSeparator', background=c['border'])
    
    def _set_app_icon(self):
        """Set the application icon."""
        try:
            icon_img = create_app_icon()
            if icon_img:
                self._icon_photo = ImageTk.PhotoImage(icon_img)
                self.iconphoto(True, self._icon_photo)
                
                # Also save as .ico file for future use
                icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sd_metaviewer.ico")
                if not os.path.exists(icon_path):
                    save_icon_file(icon_img, icon_path)
        except Exception:
            pass
    
    def _create_ui(self):
        """Create the user interface."""
        # Main container with proper layout
        self.main_frame = ttk.Frame(self, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Configure grid weights for main_frame
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1)  # Content area expands
        
        # Top toolbar container (row 0)
        toolbar_container = ttk.Frame(self.main_frame)
        toolbar_container.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        
        # Toolbar with buttons
        toolbar_row1 = ttk.Frame(toolbar_container)
        toolbar_row1.pack(fill=tk.X)
        
        ttk.Button(toolbar_row1, text="🖼 Open Image", command=self._open_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar_row1, text="📁 Open Folder", command=self._open_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar_row1, text="📋 Paste", command=self._paste_from_clipboard).pack(side=tk.LEFT, padx=5)
        
        ttk.Separator(toolbar_row1, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)
        
        ttk.Button(toolbar_row1, text="◀ Prev", command=self._prev_image, width=8).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar_row1, text="Next ▶", command=self._next_image, width=8).pack(side=tk.LEFT, padx=5)
        
        ttk.Separator(toolbar_row1, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)
        
        # Recent images dropdown
        self.recent_btn = ttk.Menubutton(toolbar_row1, text="🕒 Recent")
        self.recent_menu = tk.Menu(self.recent_btn, tearoff=0,
                                   bg=self.colors['bg_secondary'], fg=self.colors['fg'],
                                   activebackground=self.colors['accent'], activeforeground='#ffffff',
                                   selectcolor=self.colors['accent'],
                                   relief='flat', borderwidth=1,
                                   activeborderwidth=0)
        self.recent_btn['menu'] = self.recent_menu
        self.recent_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(toolbar_row1, text="❌ Close", command=self._close_current).pack(side=tk.LEFT, padx=5)
        ttk.Button(toolbar_row1, text="📂 Explorer", command=self._show_in_explorer).pack(side=tk.LEFT, padx=5)
        
        # Status label on same row
        self.history_label = ttk.Label(toolbar_row1, text="No image loaded")
        self.history_label.pack(side=tk.LEFT, padx=20)
        
        # Content area (row 1) - will hold either the main view or grid view
        self.content_frame = ttk.Frame(self.main_frame)
        self.content_frame.grid(row=1, column=0, sticky='nsew')
        self.content_frame.columnconfigure(0, weight=1)
        self.content_frame.rowconfigure(0, weight=1)
        
        # Create main viewer pane
        self._create_viewer_pane()
        
        # Status bar (row 2) - at bottom, never hidden
        self.status_var = tk.StringVar(value="Ready - Drag and drop an image to view metadata")
        status_bar = ttk.Label(self.main_frame, textvariable=self.status_var, relief='sunken', anchor='w')
        status_bar.grid(row=2, column=0, sticky='ew', pady=(10, 0))
        
        # Grid view (initially hidden)
        self.grid_frame = None
        self.grid_thumbnails = []
    
    def _create_viewer_pane(self):
        """Create the main image viewer pane."""
        # Split pane
        self.paned = ttk.PanedWindow(self.content_frame, orient=tk.HORIZONTAL)
        self.paned.grid(row=0, column=0, sticky='nsew')
        
        # Left panel - Image preview (with scrollable container)
        left_frame = ttk.Frame(self.paned, padding="5")
        self.paned.add(left_frame, weight=1)
        
        # Configure left frame to expand
        left_frame.columnconfigure(0, weight=1)
        left_frame.rowconfigure(0, weight=1)
        
        # Scrollable image container
        image_container = ttk.Frame(left_frame)
        image_container.grid(row=0, column=0, sticky='nsew')
        image_container.columnconfigure(0, weight=1)
        image_container.rowconfigure(0, weight=1)
        
        # Canvas for image display
        self.image_canvas = tk.Canvas(image_container, bg=self.colors['canvas_bg'], highlightthickness=0)
        self.image_canvas.grid(row=0, column=0, sticky='nsew')
        
        # Frame inside canvas for image
        self.image_frame = ttk.Frame(self.image_canvas)
        self.canvas_window = self.image_canvas.create_window((0, 0), window=self.image_frame, anchor='nw')
        
        self.image_label = ttk.Label(self.image_frame, text="🖼️\n\nDrag & Drop Image Here\nor\nClick 'Open Image'\n\nSupports PNG, JPG, WEBP",
                                      anchor="center", justify="center", font=('Segoe UI', 12))
        self.image_label.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Bind canvas resize
        self.image_canvas.bind('<Configure>', self._on_canvas_configure)
        self.image_frame.bind('<Configure>', self._on_frame_configure)
        
        # Image info
        self.image_info_label = ttk.Label(left_frame, text="", anchor="center")
        self.image_info_label.grid(row=1, column=0, sticky='ew', pady=(5, 0))
        
        # Right panel - Metadata display
        right_frame = ttk.Frame(self.paned, padding="5")
        self.paned.add(right_frame, weight=2)
        
        # Configure right frame
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=1)
        
        # Source info
        source_frame = ttk.Frame(right_frame)
        source_frame.grid(row=0, column=0, sticky='ew', pady=(0, 10))
        
        ttk.Label(source_frame, text="Source:", style='Header.TLabel').pack(side=tk.LEFT)
        self.source_label = ttk.Label(source_frame, text="No image loaded", style='Secondary.TLabel')
        self.source_label.pack(side=tk.LEFT, padx=10)
        
        # Notebook for different metadata views
        self.notebook = ttk.Notebook(right_frame)
        self.notebook.grid(row=1, column=0, sticky='nsew')
        
        # Formatted view tab
        formatted_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(formatted_frame, text="📝 Formatted")
        
        # Configure formatted frame for proper expansion
        formatted_frame.columnconfigure(0, weight=1)
        formatted_frame.rowconfigure(1, weight=3)  # Prompt text expands most
        formatted_frame.rowconfigure(3, weight=2)  # Negative prompt expands less
        formatted_frame.rowconfigure(5, weight=1)  # Parameters expands least
        
        # Prompt section
        prompt_label_frame = ttk.Frame(formatted_frame)
        prompt_label_frame.grid(row=0, column=0, sticky='ew')
        ttk.Label(prompt_label_frame, text="Prompt:", style='Header.TLabel').pack(side=tk.LEFT)
        ttk.Button(prompt_label_frame, text="Copy", command=self._copy_prompt, width=6).pack(side=tk.RIGHT)
        
        self.prompt_text = tk.Text(formatted_frame, height=4, wrap=tk.WORD, font=('Consolas', 10),
                                    bg=self.colors['text_bg'], fg=self.colors['fg'],
                                    insertbackground=self.colors['fg'], relief='flat', borderwidth=0,
                                    highlightbackground=self.colors['text_border'], highlightthickness=1,
                                    selectbackground=self.colors['accent'], selectforeground='#ffffff',
                                    cursor='arrow')
        self.prompt_text.grid(row=1, column=0, sticky='nsew', pady=(5, 10))
        self.prompt_text.configure(state='disabled')
        self._add_context_menu(self.prompt_text)
        
        # Negative prompt section
        neg_label_frame = ttk.Frame(formatted_frame)
        neg_label_frame.grid(row=2, column=0, sticky='ew')
        ttk.Label(neg_label_frame, text="Negative Prompt:", style='Header.TLabel').pack(side=tk.LEFT)
        ttk.Button(neg_label_frame, text="Copy", command=self._copy_negative, width=6).pack(side=tk.RIGHT)
        
        self.negative_text = tk.Text(formatted_frame, height=3, wrap=tk.WORD, font=('Consolas', 10),
                                      bg=self.colors['text_bg'], fg=self.colors['fg'],
                                      insertbackground=self.colors['fg'], relief='flat', borderwidth=0,
                                      highlightbackground=self.colors['text_border'], highlightthickness=1,
                                      selectbackground=self.colors['accent'], selectforeground='#ffffff',
                                      cursor='arrow')
        self.negative_text.grid(row=3, column=0, sticky='nsew', pady=(5, 10))
        self.negative_text.configure(state='disabled')
        self._add_context_menu(self.negative_text)
        
        # Parameters section
        ttk.Label(formatted_frame, text="Parameters:", style='Header.TLabel').grid(row=4, column=0, sticky='w')
        
        params_frame = ttk.Frame(formatted_frame)
        params_frame.grid(row=5, column=0, sticky='nsew', pady=(5, 0))
        params_frame.columnconfigure(0, weight=1)
        params_frame.rowconfigure(0, weight=1)
        
        self.params_text = tk.Text(params_frame, height=4, wrap=tk.WORD, font=('Consolas', 10),
                                    bg=self.colors['text_bg'], fg=self.colors['fg'],
                                    insertbackground=self.colors['fg'], relief='flat', borderwidth=0,
                                    highlightbackground=self.colors['text_border'], highlightthickness=1,
                                    selectbackground=self.colors['accent'], selectforeground='#ffffff',
                                    cursor='arrow')
        self.params_text.grid(row=0, column=0, sticky='nsew')
        self.params_text.configure(state='disabled')
        
        params_scroll = ttk.Scrollbar(params_frame, orient=tk.VERTICAL, command=self.params_text.yview)
        params_scroll.grid(row=0, column=1, sticky='ns')
        self.params_text.configure(yscrollcommand=params_scroll.set)
        self._add_context_menu(self.params_text)
        
        # Raw metadata tab
        raw_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(raw_frame, text="📄 Raw Data")
        raw_frame.columnconfigure(0, weight=1)
        raw_frame.rowconfigure(0, weight=1)
        
        self.raw_text = tk.Text(raw_frame, wrap=tk.WORD, font=('Consolas', 9),
                                 bg=self.colors['text_bg'], fg=self.colors['fg'],
                                 insertbackground=self.colors['fg'], relief='flat', borderwidth=0,
                                 highlightbackground=self.colors['text_border'], highlightthickness=1,
                                 selectbackground=self.colors['accent'], selectforeground='#ffffff',
                                 cursor='arrow')
        self.raw_text.grid(row=0, column=0, sticky='nsew')
        self.raw_text.configure(state='disabled')
        
        raw_scroll = ttk.Scrollbar(raw_frame, orient=tk.VERTICAL, command=self.raw_text.yview)
        raw_scroll.grid(row=0, column=1, sticky='ns')
        self.raw_text.configure(yscrollcommand=raw_scroll.set)
        self._add_context_menu(self.raw_text)
        
        # Tags view tab (easy to read)
        tags_frame = ttk.Frame(self.notebook, padding="10")
        self.notebook.add(tags_frame, text="🏷️ Tags View")
        tags_frame.columnconfigure(0, weight=1)
        tags_frame.rowconfigure(0, weight=1)
        
        self.tags_text = tk.Text(tags_frame, wrap=tk.WORD, font=('Segoe UI', 11),
                                  bg=self.colors['text_bg'], fg=self.colors['fg'],
                                  insertbackground=self.colors['fg'], relief='flat', borderwidth=0,
                                  highlightbackground=self.colors['text_border'], highlightthickness=1,
                                  selectbackground=self.colors['accent'], selectforeground='#ffffff',
                                  cursor='arrow')
        self.tags_text.grid(row=0, column=0, sticky='nsew')
        self.tags_text.configure(state='disabled')
        
        tags_scroll = ttk.Scrollbar(tags_frame, orient=tk.VERTICAL, command=self.tags_text.yview)
        tags_scroll.grid(row=0, column=1, sticky='ns')
        self.tags_text.configure(yscrollcommand=tags_scroll.set)
        self._add_context_menu(self.tags_text)
        
        # Configure text tag for tags view with theme colors
        self.tags_text.tag_configure('tag', background=self.colors['tag_bg'], foreground=self.colors['tag_fg'], 
                                      font=('Segoe UI', 10))
        self.tags_text.tag_configure('tag_neg', background=self.colors['tag_neg_bg'], foreground=self.colors['tag_neg_fg'], 
                                      font=('Segoe UI', 10))
        self.tags_text.tag_configure('header', font=('Segoe UI', 11, 'bold'), foreground=self.colors['tag_fg'],
                                      spacing1=5, spacing3=5)
        self.tags_text.tag_configure('header_neg', font=('Segoe UI', 11, 'bold'), foreground=self.colors['tag_neg_fg'],
                                      spacing1=10, spacing3=5)
    
    def _on_canvas_configure(self, event):
        """Handle canvas resize and center the image."""
        # Get canvas and frame dimensions
        canvas_width = event.width
        canvas_height = event.height
        
        # Get frame size
        frame_width = self.image_frame.winfo_reqwidth()
        frame_height = self.image_frame.winfo_reqheight()
        
        # Calculate position to center the frame
        x = max(0, (canvas_width - frame_width) // 2)
        y = max(0, (canvas_height - frame_height) // 2)
        
        # Move the window to center position
        self.image_canvas.coords(self.canvas_window, x, y)
        
        # Update scroll region
        self.image_canvas.configure(scrollregion=self.image_canvas.bbox("all"))
    
    def _on_frame_configure(self, event):
        """Handle frame resize inside canvas and recenter."""
        # Get canvas dimensions
        canvas_width = self.image_canvas.winfo_width()
        canvas_height = self.image_canvas.winfo_height()
        
        # Get frame size
        frame_width = event.width
        frame_height = event.height
        
        # Calculate position to center the frame
        x = max(0, (canvas_width - frame_width) // 2)
        y = max(0, (canvas_height - frame_height) // 2)
        
        # Move the window to center position
        self.image_canvas.coords(self.canvas_window, x, y)
        
        # Update scroll region
        self.image_canvas.configure(scrollregion=self.image_canvas.bbox("all"))
    
    def _center_image(self):
        """Center the image frame in the canvas."""
        canvas_width = self.image_canvas.winfo_width()
        canvas_height = self.image_canvas.winfo_height()
        frame_width = self.image_frame.winfo_reqwidth()
        frame_height = self.image_frame.winfo_reqheight()
        
        x = max(0, (canvas_width - frame_width) // 2)
        y = max(0, (canvas_height - frame_height) // 2)
        
        self.image_canvas.coords(self.canvas_window, x, y)
        self.image_canvas.configure(scrollregion=self.image_canvas.bbox("all"))
    
    def _show_grid_view(self):
        """Show the grid view of folder images."""
        # Hide the main viewer
        self.paned.grid_forget()
        
        # Create grid frame if needed
        if self.grid_frame:
            self.grid_frame.destroy()
        
        self.grid_frame = ttk.Frame(self.content_frame)
        self.grid_frame.grid(row=0, column=0, sticky='nsew')
        
        # Header
        header_frame = ttk.Frame(self.grid_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        folder_name = os.path.basename(self.current_folder) if self.current_folder else "Unknown"
        ttk.Label(header_frame, text=f"📁 {folder_name} ({len(self.folder_images)} images)", 
                  style='Title.TLabel').pack(side=tk.LEFT)
        ttk.Button(header_frame, text="← Back to Viewer", command=self._hide_grid_view).pack(side=tk.RIGHT)
        
        # Scrollable canvas for grid
        canvas_frame = ttk.Frame(self.grid_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(canvas_frame, bg=self.colors['bg'], highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        
        self.grid_inner_frame = ttk.Frame(canvas)
        
        canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        canvas_window = canvas.create_window((0, 0), window=self.grid_inner_frame, anchor='nw')
        
        # Bind mouse wheel
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        # Update scroll region when frame changes
        def configure_scroll(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfig(canvas_window, width=event.width)
        self.grid_inner_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind('<Configure>', configure_scroll)
        
        # Load thumbnails
        self.status_var.set("Loading thumbnails...")
        self.update_idletasks()
        self._load_grid_thumbnails()
        self.status_var.set(f"Showing {len(self.folder_images)} images from {folder_name}")
    
    def _load_grid_thumbnails(self):
        """Load thumbnails for the grid view."""
        self.grid_thumbnails = []
        
        # Calculate grid columns based on window width
        cols = 4
        thumb_size = 150
        
        for i, filepath in enumerate(self.folder_images):
            row = i // cols
            col = i % cols
            
            # Create frame for each thumbnail
            thumb_frame = ttk.Frame(self.grid_inner_frame, padding=5)
            thumb_frame.grid(row=row, column=col, padx=5, pady=5, sticky='nsew')
            
            try:
                # Load and resize thumbnail
                with Image.open(filepath) as img:
                    img.thumbnail((thumb_size, thumb_size), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.grid_thumbnails.append(photo)  # Keep reference
                    
                    # Image label
                    img_label = ttk.Label(thumb_frame, image=photo, cursor='hand2')
                    img_label.pack()
                    
                    # Bind click
                    img_label.bind('<Button-1>', lambda e, fp=filepath: self._select_from_grid(fp))
                    
                    # Filename label
                    name = os.path.basename(filepath)
                    if len(name) > 20:
                        name = name[:17] + "..."
                    name_label = ttk.Label(thumb_frame, text=name, font=('Segoe UI', 8))
                    name_label.pack()
                    name_label.bind('<Button-1>', lambda e, fp=filepath: self._select_from_grid(fp))
                    
            except Exception as e:
                # Show placeholder for failed thumbnails
                error_label = ttk.Label(thumb_frame, text="❌\nError", font=('Segoe UI', 10))
                error_label.pack(padx=20, pady=20)
            
            # Update UI periodically
            if i % 10 == 0:
                self.update_idletasks()
    
    def _select_from_grid(self, filepath: str):
        """Select an image from the grid view."""
        self._hide_grid_view()
        self._load_image(filepath)
    
    def _hide_grid_view(self):
        """Hide the grid view and show the main viewer."""
        if self.grid_frame:
            # Unbind mousewheel
            try:
                self.unbind_all("<MouseWheel>")
            except:
                pass
            self.grid_frame.destroy()
            self.grid_frame = None
            self.grid_thumbnails = []
        
        # Show main viewer
        self.paned.grid(row=0, column=0, sticky='nsew')
    
    def _add_context_menu(self, widget):
        """Add right-click context menu to a text widget."""
        menu = tk.Menu(widget, tearoff=0,
                       bg=self.colors['bg_secondary'], fg=self.colors['fg'],
                       activebackground=self.colors['accent'], activeforeground='#ffffff',
                       selectcolor=self.colors['accent'],
                       relief='flat', borderwidth=1, activeborderwidth=0)
        menu.add_command(label="Copy", command=lambda: self._copy_selection(widget), accelerator="Ctrl+C")
        menu.add_command(label="Copy All", command=lambda: self._copy_all_from_widget(widget))
        menu.add_separator()
        menu.add_command(label="Paste Image from Clipboard", command=self._paste_from_clipboard, accelerator="Ctrl+V")
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: widget.tag_add('sel', '1.0', 'end'), accelerator="Ctrl+A")
        
        def show_menu(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
        
        widget.bind("<Button-3>", show_menu)
    
    def _copy_selection(self, widget):
        """Copy selected text from widget."""
        try:
            text = widget.get('sel.first', 'sel.last')
            self.clipboard_clear()
            self.clipboard_append(text)
            self.status_var.set("Copied selection to clipboard")
        except tk.TclError:
            pass
    
    def _copy_all_from_widget(self, widget):
        """Copy all text from widget."""
        text = widget.get('1.0', 'end-1c')
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Copied all text to clipboard")
    
    def _setup_bindings(self):
        """Setup keyboard shortcuts."""
        self.bind('<Control-o>', lambda e: self._open_file())
        self.bind('<Control-c>', lambda e: self._copy_prompt())
        self.bind('<Control-v>', lambda e: self._paste_from_clipboard())
        self.bind('<Left>', lambda e: self._prev_image())
        self.bind('<Right>', lambda e: self._next_image())
        self.bind('<F5>', lambda e: self._toggle_grid_view())
        self.bind('<Escape>', lambda e: self._hide_grid_view() if self.grid_frame else None)
        
        # Bind resize event to refresh image display
        self._resize_timer = None
        self.bind('<Configure>', self._on_window_resize)
    
    def _on_window_resize(self, event):
        """Handle window resize - refresh image display after resize stops."""
        # Only respond to main window resize events
        if event.widget == self and self.current_image_path:
            # Cancel previous timer if exists
            if self._resize_timer:
                self.after_cancel(self._resize_timer)
            # Set new timer to redisplay after resize stops
            self._resize_timer = self.after(200, self._refresh_image_display)
    
    def _refresh_image_display(self):
        """Refresh the image display with current window size."""
        self._resize_timer = None
        if self.current_image_path and os.path.exists(self.current_image_path):
            self._display_image(self.current_image_path)
    
    def _adjust_initial_layout(self):
        """Adjust layout after initial window display."""
        # Set paned window sash position to give more space to metadata
        try:
            total_width = self.paned.winfo_width()
            if total_width > 100:
                # Give about 40% to image, 60% to metadata
                self.paned.sashpos(0, int(total_width * 0.40))
        except:
            pass
    
    def _toggle_grid_view(self):
        """Toggle between grid view and image viewer."""
        if self.grid_frame:
            self._hide_grid_view()
        elif self.current_folder and self.folder_images:
            self._show_grid_view()
    
    def _setup_dnd(self):
        """Setup drag and drop functionality."""
        # Bind drop events to the image label and frame
        for widget in [self.image_label, self.image_frame, self]:
            widget.drop_target_register = lambda: None
            
        # Use tkinterdnd2 if available, otherwise use Windows-specific method
        try:
            self.drop_target_register('DND_Files')
            self.dnd_bind('<<Drop>>', self._on_drop)
        except:
            # Fallback: bind to file open on click
            self.image_label.bind('<Button-1>', lambda e: self._open_file())
            
            # Try to enable basic Windows drag-drop
            try:
                import windnd
                windnd.hook_dropfiles(self, self._on_windows_drop)
            except ImportError:
                pass
    
    def _on_windows_drop(self, files):
        """Handle Windows drop event."""
        if files:
            filepath = files[0]
            # windnd returns bytes on Windows, decode to string
            if isinstance(filepath, bytes):
                filepath = filepath.decode('utf-8', errors='replace')
            self._load_image(filepath)
    
    def _on_drop(self, event):
        """Handle drag and drop event."""
        filepath = event.data
        # Clean up filepath (remove curly braces if present)
        if filepath.startswith('{') and filepath.endswith('}'):
            filepath = filepath[1:-1]
        self._load_image(filepath)
    
    def _open_file(self):
        """Open file dialog to select an image."""
        filetypes = [
            ('Image files', '*.png *.jpg *.jpeg *.webp *.bmp'),
            ('PNG files', '*.png'),
            ('JPEG files', '*.jpg *.jpeg'),
            ('WebP files', '*.webp'),
            ('All files', '*.*')
        ]
        filepath = filedialog.askopenfilename(filetypes=filetypes)
        if filepath:
            # Clear folder mode when opening single file
            self.current_folder = None
            self.folder_images = []
            self.folder_index = -1
            self._load_image(filepath)
    
    def _open_folder(self):
        """Open folder dialog to browse images in a folder."""
        folder = filedialog.askdirectory()
        if folder:
            self._load_folder(folder)
    
    def _load_folder(self, folder: str):
        """Load all images from a folder."""
        try:
            # Find all image files in folder (case-insensitive)
            extensions = ('*.png', '*.jpg', '*.jpeg', '*.webp', '*.bmp')
            images = []
            seen_paths = set()  # Track seen paths to avoid duplicates
            
            for ext in extensions:
                # Use lowercase pattern - Path.glob is case-insensitive on Windows
                for img_path in Path(folder).glob(ext):
                    normalized = str(img_path).lower()
                    if normalized not in seen_paths:
                        seen_paths.add(normalized)
                        images.append(str(img_path))
            
            # Sort by name (case-insensitive)
            images = sorted(images, key=lambda x: os.path.basename(x).lower())
            
            if not images:
                messagebox.showinfo("No Images", "No image files found in the selected folder.")
                return
            
            self.current_folder = folder
            self.folder_images = images
            self.folder_index = 0
            
            # Show grid view for folder selection
            self._show_grid_view()
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open folder:\n{str(e)}")
    
    def _close_current(self):
        """Close current image and show next, or reset if no more images."""
        # Hide grid view if showing
        if self.grid_frame:
            self._hide_grid_view()
            return
        
        # If in folder mode, remove current image from view and show next
        if self.current_folder and self.folder_images:
            if len(self.folder_images) > 1:
                # Remove current from folder list
                current_path = self.folder_images[self.folder_index]
                self.folder_images.remove(current_path)
                
                # Adjust index if needed
                if self.folder_index >= len(self.folder_images):
                    self.folder_index = len(self.folder_images) - 1
                
                # Load next image
                if self.folder_images:
                    self._load_image(self.folder_images[self.folder_index])
                    return
        
        # If in history mode with multiple images, go back
        elif self.image_history and len(self.image_history) > 1:
            # Remove current from history
            if self.history_index >= 0 and self.history_index < len(self.image_history):
                self.image_history.pop(self.history_index)
                
                # Adjust index
                if self.history_index >= len(self.image_history):
                    self.history_index = len(self.image_history) - 1
                
                if self.image_history and self.history_index >= 0:
                    self._is_navigating = True
                    try:
                        self._load_image(self.image_history[self.history_index])
                    finally:
                        self._is_navigating = False
                    return
        
        # Reset to initial state if no more images
        self.current_image_path = None
        self.current_metadata = None
        self.current_photo = None
        self.current_folder = None
        self.folder_images = []
        self.folder_index = -1
        self.image_history = []
        self.history_index = -1
        
        # Reset UI
        self.image_label.configure(image='', text="🖼️\n\nDrag & Drop Image Here\nor\nClick 'Open Image'\n\nSupports PNG, JPG, WEBP")
        self.image_info_label.configure(text="")
        self.source_label.configure(text="No image loaded")
        self._set_text(self.prompt_text, "")
        self._set_text(self.negative_text, "")
        self._set_text(self.params_text, "No parameters found")
        self._set_text(self.raw_text, "")
        self.tags_text.configure(state='normal')
        self.tags_text.delete('1.0', 'end')
        self.tags_text.configure(state='disabled')
        self.history_label.configure(text="No image loaded")
        self.status_var.set("Ready - Drag and drop an image to view metadata")
    
    def _load_image(self, filepath: str):
        """Load an image and extract its metadata."""
        try:
            self.status_var.set(f"Loading: {os.path.basename(filepath)}")
            self.update_idletasks()
            
            # Validate file exists
            if not os.path.exists(filepath):
                raise FileNotFoundError(f"File not found: {filepath}")
            
            # Extract metadata
            metadata = ImageMetadataExtractor.extract(filepath)
            
            if "error" in metadata:
                messagebox.showerror("Error", f"Failed to read image: {metadata['error']}")
                return
            
            self.current_image_path = filepath
            self.current_metadata = metadata
            
            # Add to recent images (max 20)
            if filepath not in self.recent_images:
                self.recent_images.insert(0, filepath)
                if len(self.recent_images) > 20:
                    self.recent_images = self.recent_images[:20]
                self._update_recent_menu()
            else:
                # Move to front if already exists
                self.recent_images.remove(filepath)
                self.recent_images.insert(0, filepath)
                self._update_recent_menu()
            
            # Update folder index if in folder mode (skip if navigating)
            if not self._is_navigating and self.current_folder and filepath in self.folder_images:
                self.folder_index = self.folder_images.index(filepath)
            
            # Update history (only in non-folder mode or when jumping, skip if navigating)
            if not self._is_navigating and not self.current_folder:
                if not self.image_history or self.image_history[-1] != filepath:
                    # Remove forward history if navigating from middle
                    if self.history_index < len(self.image_history) - 1:
                        self.image_history = self.image_history[:self.history_index + 1]
                    self.image_history.append(filepath)
                    self.history_index = len(self.image_history) - 1
            
            # Update display
            self._display_image(filepath)
            self._display_metadata(metadata)
            self._update_history_label()
            
            self.status_var.set(f"Loaded: {os.path.basename(filepath)}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image:\n{str(e)}")
            self.status_var.set("Error loading image")
    
    def _update_recent_menu(self):
        """Update the recent images menu."""
        self.recent_menu.delete(0, tk.END)
        
        if not self.recent_images:
            self.recent_menu.add_command(label="(No recent images)", state='disabled')
            return
        
        for filepath in self.recent_images[:10]:  # Show max 10 in menu
            filename = os.path.basename(filepath)
            if len(filename) > 40:
                filename = filename[:37] + "..."
            self.recent_menu.add_command(
                label=filename,
                command=lambda fp=filepath: self._load_image(fp)
            )
        
        if len(self.recent_images) > 10:
            self.recent_menu.add_separator()
            self.recent_menu.add_command(label=f"({len(self.recent_images)} total)", state='disabled')
        
        self.recent_menu.add_separator()
        self.recent_menu.add_command(label="Clear Recent", command=self._clear_recent)
    
    def _clear_recent(self):
        """Clear the recent images list."""
        self.recent_images = []
        self._update_recent_menu()
        self.status_var.set("Recent images cleared")
    
    def _paste_from_clipboard(self):
        """Paste image from clipboard."""
        try:
            # Try to get file path from clipboard first
            try:
                clipboard_text = self.clipboard_get()
                if clipboard_text and os.path.isfile(clipboard_text):
                    self._load_image(clipboard_text)
                    return
            except tk.TclError:
                pass
            
            # Try to get image from clipboard (Windows)
            try:
                from PIL import ImageGrab
                img = ImageGrab.grabclipboard()
                
                if img is not None:
                    if isinstance(img, list):
                        # It's a list of file paths
                        for item in img:
                            if os.path.isfile(str(item)):
                                self._load_image(str(item))
                                return
                    elif hasattr(img, 'save'):
                        # It's an image - save temporarily and load
                        import tempfile
                        temp_path = os.path.join(tempfile.gettempdir(), "sd_metaviewer_paste.png")
                        img.save(temp_path, "PNG")
                        self._load_image(temp_path)
                        self.status_var.set("Loaded image from clipboard (Note: Pasted images may not have metadata)")
                        return
            except ImportError:
                pass
            except Exception as e:
                pass
            
            self.status_var.set("No image found in clipboard")
            
        except Exception as e:
            self.status_var.set(f"Failed to paste: {str(e)}")
    
    def _display_image(self, filepath: str):
        """Display the image in the scrollable canvas."""
        try:
            with Image.open(filepath) as img:
                # Get canvas size for scaling
                self.update_idletasks()
                canvas_width = self.image_canvas.winfo_width() - 20
                canvas_height = self.image_canvas.winfo_height() - 20
                
                # Use reasonable defaults if canvas size not yet available
                if canvas_width < 100:
                    canvas_width = 400
                if canvas_height < 100:
                    canvas_height = 400
                
                # Calculate size to fit in canvas while maintaining aspect ratio
                img_width, img_height = img.size
                ratio = min(canvas_width / img_width, canvas_height / img_height, 1.0)
                
                new_width = int(img_width * ratio)
                new_height = int(img_height * ratio)
                
                # Resize with high quality
                if ratio < 1.0:
                    resized_img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                else:
                    resized_img = img.copy()
                
                # Convert to PhotoImage
                self.current_photo = ImageTk.PhotoImage(resized_img)
                
                # Update label
                self.image_label.configure(image=self.current_photo, text='')
                
                # Force update and recenter
                self.update_idletasks()
                self._center_image()
                
                # Add right-click menu for image
                self._add_image_context_menu()
                
        except Exception as e:
            self.image_label.configure(image='', text=f"Error displaying image:\n{str(e)}")
    
    def _add_image_context_menu(self):
        """Add right-click menu to image label."""
        menu = tk.Menu(
            self.image_label, 
            tearoff=0,
            bg=self.colors['bg_secondary'],
            fg=self.colors['fg'],
            activebackground=self.colors['accent'],
            activeforeground='white',
            selectcolor=self.colors['accent'],
            relief='flat', borderwidth=1, activeborderwidth=0
        )
        menu.add_command(label="Copy Image Path", command=self._copy_image_path)
        menu.add_command(label="Show in Explorer", command=self._show_in_explorer)
        menu.add_separator()
        menu.add_command(label="Copy Prompt", command=self._copy_prompt)
        menu.add_command(label="Copy All Metadata", command=self._copy_all)
        
        def show_menu(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
        
        self.image_label.bind("<Button-3>", show_menu)
    
    def _copy_image_path(self):
        """Copy the current image path to clipboard."""
        if self.current_image_path:
            self.clipboard_clear()
            self.clipboard_append(self.current_image_path)
            self.status_var.set("Image path copied to clipboard")
    
    def _show_in_explorer(self):
        """Open file explorer and select the current image."""
        if self.current_image_path and os.path.exists(self.current_image_path):
            import subprocess
            import platform
            
            if platform.system() == 'Windows':
                subprocess.run(['explorer', '/select,', self.current_image_path])
            elif platform.system() == 'Darwin':  # macOS
                subprocess.run(['open', '-R', self.current_image_path])
            else:  # Linux
                subprocess.run(['xdg-open', os.path.dirname(self.current_image_path)])
            
            self.status_var.set("Opened in file explorer")
    
    def _display_metadata(self, metadata: Dict):
        """Display the extracted metadata."""
        parsed = metadata.get("parsed", {})
        
        # Update source label
        source = metadata.get("source", "Unknown")
        self.source_label.configure(text=source)
        
        # Update prompt
        prompt = parsed.get("prompt", "")
        self._set_text(self.prompt_text, prompt)
        
        # Update negative prompt
        negative = parsed.get("negative_prompt", "")
        self._set_text(self.negative_text, negative)
        
        # Update parameters
        params = parsed.get("parameters", {})
        params_text = "\n".join([f"{k}: {v}" for k, v in params.items() if v])
        self._set_text(self.params_text, params_text if params_text else "No parameters found")
        
        # Update raw metadata
        raw = metadata.get("raw_metadata", {})
        try:
            import json
            raw_text = json.dumps(raw, indent=2, ensure_ascii=False)
        except:
            raw_text = str(raw)
        self._set_text(self.raw_text, raw_text)
        
        # Update tags view
        self._update_tags_view(parsed)
        
        # Update image info
        file_info = metadata.get("file_info", {})
        info_parts = []
        if file_info.get("size"):
            info_parts.append(file_info["size"])
        if file_info.get("file_size"):
            info_parts.append(file_info["file_size"])
        if file_info.get("format"):
            info_parts.append(file_info["format"])
        self.image_info_label.configure(text=" | ".join(info_parts))
    
    def _set_text(self, widget, text: str):
        """Set text in a Text widget."""
        widget.configure(state='normal')
        widget.delete('1.0', 'end')
        widget.insert('1.0', text)
        widget.configure(state='disabled')
    
    def _update_tags_view(self, parsed: Dict):
        """Update the tags view with parsed data."""
        self.tags_text.configure(state='normal')
        self.tags_text.delete('1.0', 'end')
        
        prompt = parsed.get("prompt", "")
        if prompt:
            self.tags_text.insert('end', "Prompt Tags:\n", 'header')
            # Split by common delimiters (comma, newline)
            import re
            tags = re.split(r',|\n', prompt)
            for tag in tags:
                tag = tag.strip()
                if tag:
                    # Insert tag with styling
                    self.tags_text.insert('end', "  ")
                    self.tags_text.insert('end', tag, 'tag')
                    self.tags_text.insert('end', "\n")
            self.tags_text.insert('end', "\n")
        
        negative = parsed.get("negative_prompt", "")
        if negative:
            self.tags_text.insert('end', "Negative Tags:\n", 'header_neg')
            tags = re.split(r',|\n', negative)
            for tag in tags:
                tag = tag.strip()
                if tag:
                    self.tags_text.insert('end', "  ")
                    self.tags_text.insert('end', tag, 'tag_neg')
                    self.tags_text.insert('end', "\n")
        
        self.tags_text.configure(state='disabled')
    
    def _copy_prompt(self):
        """Copy the prompt to clipboard."""
        if self.current_metadata:
            prompt = self.current_metadata.get("parsed", {}).get("prompt", "")
            if prompt:
                self.clipboard_clear()
                self.clipboard_append(prompt)
                self.status_var.set("Prompt copied to clipboard")
            else:
                self.status_var.set("No prompt to copy")
    
    def _copy_negative(self):
        """Copy the negative prompt to clipboard."""
        if self.current_metadata:
            negative = self.current_metadata.get("parsed", {}).get("negative_prompt", "")
            if negative:
                self.clipboard_clear()
                self.clipboard_append(negative)
                self.status_var.set("Negative prompt copied to clipboard")
            else:
                self.status_var.set("No negative prompt to copy")
    
    def _copy_all(self):
        """Copy all metadata to clipboard."""
        if self.current_metadata:
            parsed = self.current_metadata.get("parsed", {})
            text_parts = []
            
            if parsed.get("prompt"):
                text_parts.append(f"Prompt:\n{parsed['prompt']}")
            if parsed.get("negative_prompt"):
                text_parts.append(f"\nNegative Prompt:\n{parsed['negative_prompt']}")
            if parsed.get("parameters"):
                params_text = "\n".join([f"{k}: {v}" for k, v in parsed["parameters"].items() if v])
                if params_text:
                    text_parts.append(f"\nParameters:\n{params_text}")
            
            if text_parts:
                self.clipboard_clear()
                self.clipboard_append("\n".join(text_parts))
                self.status_var.set("All metadata copied to clipboard")
            else:
                self.status_var.set("No metadata to copy")
    
    def _prev_image(self):
        """Navigate to previous image."""
        self._is_navigating = True
        try:
            if self.current_folder and self.folder_images:
                # Folder mode - navigate within folder
                if self.folder_index > 0:
                    self.folder_index -= 1
                    self._load_image(self.folder_images[self.folder_index])
            elif self.history_index > 0:
                # History mode
                self.history_index -= 1
                self._load_image(self.image_history[self.history_index])
        finally:
            self._is_navigating = False
    
    def _next_image(self):
        """Navigate to next image."""
        self._is_navigating = True
        try:
            if self.current_folder and self.folder_images:
                # Folder mode - navigate within folder
                if self.folder_index < len(self.folder_images) - 1:
                    self.folder_index += 1
                    self._load_image(self.folder_images[self.folder_index])
            elif self.history_index < len(self.image_history) - 1:
                # History mode
                self.history_index += 1
                self._load_image(self.image_history[self.history_index])
        finally:
            self._is_navigating = False
    
    def _update_history_label(self):
        """Update the history navigation label."""
        filename = os.path.basename(self.current_image_path) if self.current_image_path else ""
        
        if self.current_folder and self.folder_images:
            # Folder mode
            current = self.folder_index + 1
            total = len(self.folder_images)
            folder_name = os.path.basename(self.current_folder)
            self.history_label.configure(text=f"📁 {folder_name}: {filename} ({current}/{total}) [Grid: F5]")
        elif self.image_history:
            # History mode
            current = self.history_index + 1
            total = len(self.image_history)
            self.history_label.configure(text=f"{filename} ({current}/{total})")
        else:
            self.history_label.configure(text="No image loaded")


def main():
    """Main entry point."""
    try:
        # Try to use windnd for better drag-drop on Windows
        try:
            import windnd
        except ImportError:
            pass
        
        app = SDMetaViewer()
        app.mainloop()
    except Exception as e:
        messagebox.showerror("Fatal Error", f"Application failed to start:\n{str(e)}")


if __name__ == "__main__":
    main()
