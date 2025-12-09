"""
Utility functions for SD MetaViewer.
"""

import os
from PIL import Image, ImageDraw, ImageTk


def create_app_icon():
    """Create application icon programmatically at high resolution for crisp display."""
    try:
        # Create at 256x256 for crisp display on high-DPI screens and large thumbnails
        size = 256
        scale = size / 64  # Scale factor from original 64x64 design
        img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        
        draw = ImageDraw.Draw(img)
        
        # Helper to scale coordinates
        def s(val):
            return int(val * scale)
        
        # Background - rounded rectangle effect
        draw.rounded_rectangle([s(4), s(4), s(60), s(60)], radius=s(6), fill='#4A90D9', outline='#2E5A8C', width=s(2))
        
        # Inner frame (image area)
        draw.rounded_rectangle([s(8), s(8), s(44), s(44)], radius=s(3), fill='#FFFFFF', outline='#2E5A8C', width=s(1))
        
        # Simple mountain/landscape icon inside
        draw.polygon([
            (s(12), s(40)), (s(22), s(25)), (s(32), s(35)), (s(40), s(20)), (s(40), s(40))
        ], fill='#7BC47F')
        draw.ellipse([s(30), s(12), s(38), s(20)], fill='#FFD700')  # Sun
        
        # Metadata lines on the right side
        draw.rounded_rectangle([s(48), s(10), s(56), s(14)], radius=s(1), fill='#FFFFFF')
        draw.rounded_rectangle([s(48), s(18), s(56), s(22)], radius=s(1), fill='#FFFFFF')
        draw.rounded_rectangle([s(48), s(26), s(56), s(30)], radius=s(1), fill='#FFFFFF')
        draw.rounded_rectangle([s(48), s(34), s(52), s(38)], radius=s(1), fill='#FFFFFF')
        
        return img
    except Exception:
        return None


def save_icon_file(icon_img, filepath):
    """Save icon image as .ico file with multiple sizes for crisp display."""
    try:
        # Create multiple sizes for ICO - include larger sizes for high-DPI and thumbnails
        icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        icons = []
        for size in icon_sizes:
            resized = icon_img.resize(size, Image.Resampling.LANCZOS)
            icons.append(resized)
        # Save largest first, append smaller sizes
        icons[-1].save(filepath, format='ICO', append_images=icons[:-1])
        return True
    except Exception:
        return False
