"""
Utility functions for SD MetaViewer.
"""

import os
from PIL import Image, ImageDraw, ImageTk


def create_app_icon():
    """Create application icon programmatically."""
    try:
        # Create a simple icon: a picture frame with metadata lines
        size = 64
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        
        draw = ImageDraw.Draw(img)
        
        # Background - rounded rectangle effect
        draw.rectangle([4, 4, 60, 60], fill='#4A90D9', outline='#2E5A8C', width=2)
        
        # Inner frame (image area)
        draw.rectangle([8, 8, 44, 44], fill='#FFFFFF', outline='#2E5A8C', width=1)
        
        # Simple mountain/landscape icon inside
        draw.polygon([(12, 40), (22, 25), (32, 35), (40, 20), (40, 40)], fill='#7BC47F')
        draw.ellipse([30, 12, 38, 20], fill='#FFD700')  # Sun
        
        # Metadata lines on the right side
        draw.rectangle([48, 10, 56, 14], fill='#FFFFFF')
        draw.rectangle([48, 18, 56, 22], fill='#FFFFFF')
        draw.rectangle([48, 26, 56, 30], fill='#FFFFFF')
        draw.rectangle([48, 34, 52, 38], fill='#FFFFFF')
        
        return img
    except Exception:
        return None


def save_icon_file(icon_img, filepath):
    """Save icon image as .ico file."""
    try:
        # Create multiple sizes for ICO
        icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64)]
        icons = []
        for size in icon_sizes:
            resized = icon_img.resize(size, Image.Resampling.LANCZOS)
            icons.append(resized)
        icons[0].save(filepath, format='ICO', sizes=[(s[0], s[1]) for s in icon_sizes])
        return True
    except Exception:
        return False
