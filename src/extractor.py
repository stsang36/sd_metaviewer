"""Image metadata extraction utilities."""

import json
import os
import re
import struct
from typing import Dict, Any, Optional, List, Tuple
from PIL import Image

from .parsers import MetadataParser


# Pre-compile regex patterns at module load for performance
def _compile_patterns(patterns_dict: Dict[str, List[str]]) -> List[Tuple[str, re.Pattern]]:
    """Pre-compile regex patterns for faster matching."""
    compiled = []
    for name, patterns in patterns_dict.items():
        for pattern in patterns:
            compiled.append((name, re.compile(pattern, re.IGNORECASE)))
    return compiled


# Raw patterns (for reference)
_MODEL_PATTERNS_RAW = {
    # Flux models
    'Flux.1 Dev': [r'flux.*dev', r'flux1.*dev', r'flux-dev'],
    'Flux.1 Schnell': [r'flux.*schnell', r'flux1.*schnell'],
    'Flux': [r'flux', r'Flux'],
    # SDXL variants
    'Pony Diffusion': [r'pony', r'ponyDiffusion', r'autismmix.*pony', r'pdxl'],
    'Illustrious XL': [r'illustrious', r'illustriousXL', r'noobai.*xl', r'waiANIMIXPONYXL'],
    'SDXL': [r'sdxl', r'sd_xl', r'stable.*diffusion.*xl', r'juggernaut.*xl', r'realvis.*xl', r'dreamshaperXL', r'animagine.*xl'],
    # SD 1.5 variants
    'SD 1.5': [r'sd.*1\.5', r'sd15', r'v1-5', r'stable.*diffusion.*1\.5', r'dreamshaper', r'realistic.*vision', r'deliberate'],
    # SD 2.x
    'SD 2.1': [r'sd.*2\.1', r'sd21', r'v2-1', r'stable.*diffusion.*2'],
    # SD 3
    'SD 3': [r'sd3', r'stable.*diffusion.*3', r'sd_3'],
    # Other popular models
    'Cascade': [r'cascade', r'stable.*cascade'],
    'Playground': [r'playground'],
    'PixArt': [r'pixart'],
    'Kandinsky': [r'kandinsky'],
    'Midjourney': [r'midjourney', r'mj'],
    'DALL-E': [r'dall-?e', r'dalle'],
    'AuraFlow': [r'auraflow'],
}

# Pre-compiled patterns (loaded once at import time)
_COMPILED_MODEL_PATTERNS = _compile_patterns(_MODEL_PATTERNS_RAW)


class ImageMetadataExtractor:
    """Extracts metadata from image files."""
    
    # Output prefix patterns (like z-image from ComfyUI)
    OUTPUT_PREFIX_PATTERNS = {
        'z-image': 'ComfyUI (z-image)',
        'comfyui': 'ComfyUI',
    }
    
    @classmethod
    def detect_model_architecture(cls, parsed_data: Dict, raw_metadata: Dict) -> Optional[str]:
        """Detect the model architecture from parsed data and metadata."""
        # Collect all text to search for model hints
        search_texts = []
        
        # Model name from parameters
        model_name = parsed_data.get("parameters", {}).get("model", "")
        if model_name:
            search_texts.append(model_name.lower())
        
        # Check all models list (ComfyUI)
        models = parsed_data.get("models", [])
        for m in models:
            if m:
                search_texts.append(str(m).lower())
        
        # Check LoRAs for hints (some LoRAs are model-specific)
        loras = parsed_data.get("loras", [])
        for lora in loras:
            if lora:
                search_texts.append(str(lora).lower())
        
        # Check CLIP model names
        clip_name = parsed_data.get("parameters", {}).get("clip", "")
        if clip_name:
            search_texts.append(clip_name.lower())
        
        # Check raw metadata for model hints
        for key in ['Model', 'model', 'ckpt_name', 'unet_name']:
            if key in raw_metadata:
                search_texts.append(str(raw_metadata[key]).lower())
        
        # Search using pre-compiled patterns (faster)
        combined_text = " ".join(search_texts)
        
        for arch_name, compiled_pattern in _COMPILED_MODEL_PATTERNS:
            if compiled_pattern.search(combined_text):
                return arch_name
        
        # Fallback: detect from ComfyUI node types
        workflow = parsed_data.get("workflow")
        if workflow and isinstance(workflow, dict):
            for node_id, node in workflow.items():
                if not isinstance(node, dict):
                    continue
                class_type = node.get("class_type", "")
                
                # Flux-specific nodes
                if "Flux" in class_type or "FLUX" in class_type:
                    return "Flux"
                
                # SDXL-specific nodes
                if "SDXL" in class_type or class_type in ["EmptySDXLLatentImage", "CLIPTextEncodeSDXL"]:
                    return "SDXL"
                
                # SD3-specific nodes
                if "SD3" in class_type or class_type == "EmptySD3LatentImage":
                    return "SD 3"
                
                # Cascade nodes
                if "Cascade" in class_type or "StableCascade" in class_type:
                    return "Cascade"
        
        # Detect from image size (heuristic)
        size = parsed_data.get("parameters", {}).get("size", "")
        if size:
            try:
                w, h = map(int, size.lower().split('x'))
                # SDXL typically uses 1024x1024 or similar large sizes
                if w >= 1024 or h >= 1024:
                    # Could be SDXL, but don't assume without other hints
                    pass
            except:
                pass
        
        return None
    
    @staticmethod
    def _detect_gemini(metadata: Dict) -> Optional[Dict[str, Any]]:
        """Detect if image was generated by Google Gemini via XMP metadata."""
        # Check for XMP metadata with Google AI credit
        xmp_data = metadata.get('xmp', b'')
        if isinstance(xmp_data, bytes):
            xmp_data = xmp_data.decode('utf-8', errors='ignore')
        
        xml_xmp = metadata.get('XML:com.adobe.xmp', '')
        if isinstance(xml_xmp, bytes):
            xml_xmp = xml_xmp.decode('utf-8', errors='ignore')
        
        combined_xmp = xmp_data + xml_xmp
        
        if 'Made with Google AI' in combined_xmp or 'Google AI' in combined_xmp:
            # Extract date if available
            result = {
                'source': 'Google Gemini',
                'credit': 'Made with Google AI'
            }
            
            # Try to extract creation date
            date_match = re.search(r'DateTimeOriginal="([^"]+)"', combined_xmp)
            if date_match:
                result['created'] = date_match.group(1)
            
            return result
        
        return None
    
    @staticmethod
    def _detect_chatgpt(filepath: str) -> Optional[Dict[str, Any]]:
        """Detect if image was generated by ChatGPT/OpenAI via C2PA metadata in caBX chunk."""
        try:
            with open(filepath, 'rb') as f:
                # Check PNG signature
                sig = f.read(8)
                if sig != b'\x89PNG\r\n\x1a\n':
                    return None
                
                # Read chunks
                while True:
                    try:
                        length_bytes = f.read(4)
                        if len(length_bytes) < 4:
                            break
                        length = struct.unpack('>I', length_bytes)[0]
                        chunk_type = f.read(4).decode('ascii', errors='ignore')
                        
                        if chunk_type == 'caBX':
                            # Found C2PA chunk - read it
                            chunk_data = f.read(length)
                            f.read(4)  # CRC
                            
                            # Check for ChatGPT/OpenAI markers
                            chunk_text = chunk_data.decode('utf-8', errors='ignore')
                            
                            result = {}
                            
                            if 'ChatGPT' in chunk_text or 'GPT-4o' in chunk_text or 'openai' in chunk_text.lower():
                                result['source'] = 'ChatGPT / OpenAI'
                                
                                # Extract model name
                                if 'GPT-4o' in chunk_text:
                                    result['model'] = 'GPT-4o'
                                elif 'GPT-4' in chunk_text:
                                    result['model'] = 'GPT-4'
                                elif 'DALL-E' in chunk_text or 'dall-e' in chunk_text.lower():
                                    result['model'] = 'DALL-E'
                                
                                return result
                        
                        elif chunk_type == 'IEND':
                            break
                        else:
                            # Skip chunk data and CRC
                            f.seek(length + 4, 1)
                    except:
                        break
        except:
            pass
        
        return None
    
    @staticmethod
    def _detect_editing_software(metadata: Dict, filepath: str) -> Optional[List[str]]:
        """Detect if image was edited with known software (Photoshop, GIMP, etc.)."""
        detected_software = []
        
        # Known software patterns - more specific to avoid false positives
        software_patterns = {
            'Adobe Photoshop': [r'adobe\s*photoshop\s*\d', r'photoshop\s*(cc|cs|elements|\d)', r'save.*photoshop'],
            'Adobe Lightroom': [r'lightroom', r'adobe\s+lightroom'],
            'Adobe Illustrator': [r'adobe\s*illustrator'],
            'GIMP': [r'\bgimp\b'],
            'Paint.NET': [r'paint\.net', r'paintdotnet'],
            'Affinity Photo': [r'affinity\s*photo'],
            'Affinity Designer': [r'affinity\s*designer'],
            'Pixelmator': [r'pixelmator'],
            'Capture One': [r'capture\s*one'],
            'DxO': [r'\bdxo\b'],
            'Topaz': [r'topaz\s*(denoise|sharpen|gigapixel|photo|studio)'],
            'Luminar': [r'luminar'],
            'Snapseed': [r'snapseed'],
            'Canva': [r'\bcanva\b'],
            'Figma': [r'\bfigma\b'],
            'Sketch': [r'sketch\s*app', r'bohemian.*sketch'],
            'Procreate': [r'procreate'],
            'Krita': [r'\bkrita\b'],
            'Corel': [r'corel\s*(draw|photo|painter)', r'paintshop\s*pro'],
            'ACDSee': [r'acdsee'],
            'XnView': [r'xnview'],
            'IrfanView': [r'irfanview'],
            'Preview (macOS)': [r'preview\.app'],
            'Photos (Apple)': [r'photos\s+\d', r'apple\s+photos'],
            'Windows Photos': [r'microsoft\s+photos'],
        }
        
        # Collect specific text to search (not general XMP namespaces)
        search_texts = []
        
        # Check Software tag (common in PNG/EXIF) - this is reliable
        software_tag = metadata.get('Software', '') or metadata.get('software', '')
        if software_tag:
            search_texts.append(str(software_tag))
        
        # Check XMP CreatorTool specifically (not the whole XMP)
        xmp_data = metadata.get('xmp', b'')
        if isinstance(xmp_data, bytes):
            xmp_data = xmp_data.decode('utf-8', errors='ignore')
        xml_xmp = metadata.get('XML:com.adobe.xmp', '')
        if isinstance(xml_xmp, bytes):
            xml_xmp = xml_xmp.decode('utf-8', errors='ignore')
        
        combined_xmp = xmp_data + xml_xmp
        
        # Extract CreatorTool from XMP - this is the actual editing software
        creator_match = re.search(r'CreatorTool["\s>=]+([^<"]+)', combined_xmp)
        if creator_match:
            search_texts.append(creator_match.group(1))
        
        # Extract xmp:CreatorTool attribute
        creator_attr = re.search(r'xmp:CreatorTool="([^"]+)"', combined_xmp)
        if creator_attr:
            search_texts.append(creator_attr.group(1))
        
        # Extract tiff:Software
        tiff_software = re.search(r'tiff:Software="([^"]+)"', combined_xmp)
        if tiff_software:
            search_texts.append(tiff_software.group(1))
        
        # Check for History entries indicating editing
        history_match = re.search(r'stEvt:softwareAgent="([^"]+)"', combined_xmp)
        if history_match:
            search_texts.append(history_match.group(1))
        
        # Check EXIF Software tag
        exif_data = metadata.get('exif', {})
        if isinstance(exif_data, dict):
            # Tag 305 is Software in EXIF
            exif_software = exif_data.get(305, '')
            if exif_software:
                search_texts.append(str(exif_software))
        
        # Check for Adobe JPEG APP14 marker (indicates Adobe software processed the image)
        # The 'adobe' key in metadata means the image was saved with Adobe software
        has_adobe_marker = 'adobe' in metadata or 'adobe_transform' in metadata
        
        # Check for C2PA history (used by Photoshop, etc.)
        try:
            with open(filepath, 'rb') as f:
                sig = f.read(8)
                if sig == b'\x89PNG\r\n\x1a\n':
                    while True:
                        try:
                            length_bytes = f.read(4)
                            if len(length_bytes) < 4:
                                break
                            length = struct.unpack('>I', length_bytes)[0]
                            chunk_type = f.read(4).decode('ascii', errors='ignore')
                            
                            if chunk_type == 'caBX':
                                chunk_data = f.read(length)
                                chunk_text = chunk_data.decode('utf-8', errors='ignore')
                                # Look for specific software mentions in C2PA
                                if 'softwareAgent' in chunk_text:
                                    agent_match = re.search(r'softwareAgent[^}]*name["\s:]+([^"}\]]+)', chunk_text)
                                    if agent_match:
                                        search_texts.append(agent_match.group(1))
                                f.read(4)  # CRC
                            elif chunk_type == 'IEND':
                                break
                            else:
                                f.seek(length + 4, 1)
                        except:
                            break
        except:
            pass
        
        # Search for software patterns
        combined_text = ' '.join(search_texts).lower()
        
        for software_name, patterns in software_patterns.items():
            for pattern in patterns:
                if re.search(pattern, combined_text, re.IGNORECASE):
                    if software_name not in detected_software:
                        detected_software.append(software_name)
                    break
        
        # If Adobe JPEG marker found but no specific Adobe software detected, add generic Adobe
        if has_adobe_marker and not any('Adobe' in s for s in detected_software):
            detected_software.append('Adobe (unknown program)')
        
        return detected_software if detected_software else None
    
    # EXIF tag IDs for reference
    EXIF_TAGS = {
        # Camera info
        271: 'Make',
        272: 'Model',
        305: 'Software',
        306: 'DateTime',
        # Exposure info
        33434: 'ExposureTime',
        33437: 'FNumber',
        34850: 'ExposureProgram',
        34855: 'ISOSpeedRatings',
        36867: 'DateTimeOriginal',
        36868: 'DateTimeDigitized',
        37377: 'ShutterSpeedValue',
        37378: 'ApertureValue',
        37379: 'BrightnessValue',
        37380: 'ExposureBiasValue',
        37381: 'MaxApertureValue',
        37383: 'MeteringMode',
        37384: 'LightSource',
        37385: 'Flash',
        37386: 'FocalLength',
        41486: 'FocalPlaneXResolution',
        41487: 'FocalPlaneYResolution',
        41488: 'FocalPlaneResolutionUnit',
        41495: 'SensingMethod',
        41985: 'CustomRendered',
        41986: 'ExposureMode',
        41987: 'WhiteBalance',
        41988: 'DigitalZoomRatio',
        41989: 'FocalLengthIn35mmFilm',
        41990: 'SceneCaptureType',
        42034: 'LensInfo',
        42035: 'LensMake',
        42036: 'LensModel',
        # GPS info
        1: 'GPSLatitudeRef',
        2: 'GPSLatitude',
        3: 'GPSLongitudeRef',
        4: 'GPSLongitude',
        5: 'GPSAltitudeRef',
        6: 'GPSAltitude',
        # Image info
        274: 'Orientation',
        282: 'XResolution',
        283: 'YResolution',
        296: 'ResolutionUnit',
        40961: 'ColorSpace',
        40962: 'PixelXDimension',
        40963: 'PixelYDimension',
        # Artist/Copyright
        315: 'Artist',
        33432: 'Copyright',
        37510: 'UserComment',
        40092: 'XPComment',
        40093: 'XPAuthor',
        40094: 'XPKeywords',
        40095: 'XPSubject',
    }
    
    @staticmethod
    def _convert_gps_to_decimal(gps_coords, gps_ref) -> Optional[float]:
        """Convert GPS coordinates from degrees/minutes/seconds to decimal."""
        try:
            if isinstance(gps_coords, tuple) and len(gps_coords) == 3:
                degrees = float(gps_coords[0])
                minutes = float(gps_coords[1])
                seconds = float(gps_coords[2])
                decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
                if gps_ref in ('S', 'W'):
                    decimal = -decimal
                return round(decimal, 6)
        except:
            pass
        return None
    
    @staticmethod
    def _format_exposure_time(value) -> str:
        """Format exposure time as a fraction."""
        try:
            if isinstance(value, tuple):
                num, denom = value
                if denom > num:
                    return f"1/{int(denom/num)}s"
                else:
                    return f"{num/denom}s"
            elif isinstance(value, float):
                if value < 1:
                    return f"1/{int(1/value)}s"
                return f"{value}s"
        except:
            pass
        return str(value)
    
    @staticmethod
    def _extract_camera_and_exif(metadata: Dict, img) -> Dict[str, Any]:
        """Extract camera info, GPS location, and other useful EXIF metadata."""
        camera_info = {}
        
        exif_data = metadata.get('exif', {})
        if not isinstance(exif_data, dict):
            return camera_info
        
        # Camera make and model
        make = exif_data.get(271, '')  # Make
        model = exif_data.get(272, '')  # Model
        if make or model:
            camera = f"{make} {model}".strip()
            if camera:
                camera_info['camera'] = camera
        
        # Lens info
        lens_make = exif_data.get(42035, '')  # LensMake
        lens_model = exif_data.get(42036, '')  # LensModel
        if lens_make or lens_model:
            lens = f"{lens_make} {lens_model}".strip()
            if lens:
                camera_info['lens'] = lens
        
        # Exposure settings
        exposure_parts = []
        
        # Shutter speed / Exposure time
        exposure_time = exif_data.get(33434)  # ExposureTime
        if exposure_time:
            exposure_parts.append(ImageMetadataExtractor._format_exposure_time(exposure_time))
        
        # Aperture (F-number)
        fnumber = exif_data.get(33437)  # FNumber
        if fnumber:
            try:
                if isinstance(fnumber, tuple):
                    f_val = fnumber[0] / fnumber[1]
                else:
                    f_val = float(fnumber)
                exposure_parts.append(f"f/{f_val:.1f}")
            except:
                pass
        
        # ISO
        iso = exif_data.get(34855)  # ISOSpeedRatings
        if iso:
            if isinstance(iso, tuple):
                iso = iso[0]
            exposure_parts.append(f"ISO {iso}")
        
        # Focal length
        focal = exif_data.get(37386)  # FocalLength
        if focal:
            try:
                if isinstance(focal, tuple):
                    focal_val = focal[0] / focal[1]
                else:
                    focal_val = float(focal)
                exposure_parts.append(f"{focal_val:.0f}mm")
            except:
                pass
        
        if exposure_parts:
            camera_info['exposure'] = ' | '.join(exposure_parts)
        
        # Focal length in 35mm equivalent
        focal_35mm = exif_data.get(41989)  # FocalLengthIn35mmFilm
        if focal_35mm:
            camera_info['focal_length_35mm'] = f"{focal_35mm}mm (35mm equiv.)"
        
        # Flash
        flash = exif_data.get(37385)  # Flash
        if flash is not None:
            flash_modes = {
                0: 'No Flash',
                1: 'Flash Fired',
                5: 'Flash Fired, Strobe Return',
                7: 'Flash Fired, Strobe Return',
                9: 'Flash Fired, Compulsory',
                13: 'Flash Fired, Compulsory, Return',
                15: 'Flash Fired, Compulsory, Return',
                16: 'No Flash (Compulsory)',
                24: 'No Flash (Auto)',
                25: 'Flash Fired (Auto)',
                29: 'Flash Fired (Auto), Return',
                31: 'Flash Fired (Auto), Return',
                32: 'No Flash Function',
                65: 'Flash Fired, Red-eye',
                69: 'Flash Fired, Red-eye, Return',
                71: 'Flash Fired, Red-eye, Return',
                73: 'Flash Fired, Compulsory, Red-eye',
                77: 'Flash Fired, Compulsory, Red-eye, Return',
                79: 'Flash Fired, Compulsory, Red-eye, Return',
                89: 'Flash Fired, Auto, Red-eye',
                93: 'Flash Fired, Auto, Red-eye, Return',
                95: 'Flash Fired, Auto, Red-eye, Return',
            }
            camera_info['flash'] = flash_modes.get(flash, f"Flash: {flash}")
        
        # Date taken
        date_original = exif_data.get(36867)  # DateTimeOriginal
        if date_original:
            camera_info['date_taken'] = str(date_original)
        elif exif_data.get(306):  # DateTime
            camera_info['date_taken'] = str(exif_data.get(306))
        
        # GPS Location
        gps_info = exif_data.get(34853, {})  # GPSInfo tag
        if isinstance(gps_info, dict):
            lat = gps_info.get(2)  # GPSLatitude
            lat_ref = gps_info.get(1)  # GPSLatitudeRef
            lon = gps_info.get(4)  # GPSLongitude
            lon_ref = gps_info.get(3)  # GPSLongitudeRef
            
            if lat and lon:
                lat_decimal = ImageMetadataExtractor._convert_gps_to_decimal(lat, lat_ref)
                lon_decimal = ImageMetadataExtractor._convert_gps_to_decimal(lon, lon_ref)
                
                if lat_decimal is not None and lon_decimal is not None:
                    camera_info['gps_coordinates'] = f"{lat_decimal}, {lon_decimal}"
                    camera_info['gps_maps_url'] = f"https://www.google.com/maps?q={lat_decimal},{lon_decimal}"
            
            # Altitude
            alt = gps_info.get(6)  # GPSAltitude
            alt_ref = gps_info.get(5, 0)  # GPSAltitudeRef (0 = above sea level)
            if alt:
                try:
                    if isinstance(alt, tuple):
                        alt_val = alt[0] / alt[1]
                    else:
                        alt_val = float(alt)
                    if alt_ref == 1:  # Below sea level
                        alt_val = -alt_val
                    camera_info['gps_altitude'] = f"{alt_val:.1f}m"
                except:
                    pass
        
        # Artist/Copyright
        artist = exif_data.get(315)  # Artist
        if artist:
            camera_info['artist'] = str(artist)
        
        copyright_info = exif_data.get(33432)  # Copyright
        if copyright_info:
            camera_info['copyright'] = str(copyright_info)
        
        # White balance
        wb = exif_data.get(41987)  # WhiteBalance
        if wb is not None:
            wb_modes = {0: 'Auto', 1: 'Manual'}
            camera_info['white_balance'] = wb_modes.get(wb, f"WB: {wb}")
        
        # Metering mode
        metering = exif_data.get(37383)  # MeteringMode
        if metering is not None:
            metering_modes = {
                0: 'Unknown',
                1: 'Average',
                2: 'Center-weighted',
                3: 'Spot',
                4: 'Multi-spot',
                5: 'Pattern',
                6: 'Partial',
            }
            camera_info['metering_mode'] = metering_modes.get(metering, f"Metering: {metering}")
        
        # Color space
        color_space = exif_data.get(40961)  # ColorSpace
        if color_space is not None:
            color_spaces = {1: 'sRGB', 2: 'Adobe RGB', 65535: 'Uncalibrated'}
            camera_info['color_space'] = color_spaces.get(color_space, f"ColorSpace: {color_space}")
        
        return camera_info
    
    @staticmethod
    def extract(filepath: str) -> Dict[str, Any]:
        """Extract all available metadata from an image file."""
        result = {
            "source": "Unknown",
            "raw_metadata": {},
            "parsed": {
                "prompt": "",
                "negative_prompt": "",
                "parameters": {}
            },
            "file_info": {}
        }
        
        try:
            with Image.open(filepath) as img:
                # File info
                result["file_info"] = {
                    "filename": os.path.basename(filepath),
                    "filepath": filepath,
                    "size": f"{img.width}x{img.height}",
                    "format": img.format,
                    "mode": img.mode,
                    "file_size": f"{os.path.getsize(filepath) / 1024:.1f} KB"
                }
                
                # Get all metadata
                metadata = {}
                
                # PNG chunks
                if hasattr(img, 'info'):
                    metadata.update(img.info)
                
                # Check for EXIF
                if hasattr(img, '_getexif') and img._getexif():
                    exif = img._getexif()
                    if exif:
                        metadata['exif'] = exif
                
                result["raw_metadata"] = {k: str(v)[:5000] for k, v in metadata.items()}
                
                # Debug: store keys found
                result["raw_metadata"]["_keys_found"] = str(list(metadata.keys()))
                
                # Try to identify source and parse
                # Check for ComfyUI first (can have both 'prompt' and 'workflow' keys)
                comfyui_workflow = None
                
                if 'prompt' in metadata:
                    try:
                        prompt_data = metadata['prompt']
                        if isinstance(prompt_data, str):
                            parsed_json = json.loads(prompt_data)
                            if isinstance(parsed_json, dict):
                                # Check if it looks like a ComfyUI workflow
                                is_comfyui = any(
                                    isinstance(v, dict) and 'class_type' in v 
                                    for v in parsed_json.values()
                                )
                                if is_comfyui:
                                    comfyui_workflow = parsed_json
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                if 'workflow' in metadata and not comfyui_workflow:
                    try:
                        wf_data = metadata['workflow']
                        if isinstance(wf_data, str):
                            parsed_json = json.loads(wf_data)
                            if isinstance(parsed_json, dict):
                                is_comfyui = any(
                                    isinstance(v, dict) and 'class_type' in v 
                                    for v in parsed_json.values()
                                )
                                if is_comfyui:
                                    comfyui_workflow = parsed_json
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                if comfyui_workflow:
                    result["source"] = "ComfyUI"
                    result["parsed"] = MetadataParser.parse_comfyui(comfyui_workflow)
                    
                    # Detect model architecture
                    arch = ImageMetadataExtractor.detect_model_architecture(result["parsed"], metadata)
                    if arch:
                        result["parsed"]["parameters"]["architecture"] = arch
                    
                    # Get output prefix (like z-image)
                    prefix = result["parsed"].get("parameters", {}).get("output_prefix", "")
                    
                    # Build source string
                    if arch and prefix:
                        result["source"] = f"ComfyUI / {arch} ({prefix})"
                    elif arch:
                        result["source"] = f"ComfyUI / {arch}"
                    elif prefix:
                        result["source"] = f"ComfyUI ({prefix})"
                
                elif 'parameters' in metadata:
                    # AUTOMATIC1111 format
                    result["source"] = "AUTOMATIC1111 / Stable Diffusion WebUI"
                    result["parsed"] = MetadataParser.parse_auto1111(metadata['parameters'])
                    # Detect model architecture
                    arch = ImageMetadataExtractor.detect_model_architecture(result["parsed"], metadata)
                    if arch:
                        result["parsed"]["parameters"]["architecture"] = arch
                        result["source"] = f"AUTOMATIC1111 / {arch}"
                
                elif 'Comment' in metadata or 'Description' in metadata:
                    # NovelAI format
                    result["source"] = "NovelAI"
                    result["parsed"] = MetadataParser.parse_novelai(metadata)
                
                elif 'Software' in metadata and 'NovelAI' in str(metadata.get('Software', '')):
                    result["source"] = "NovelAI"
                    result["parsed"] = MetadataParser.parse_novelai(metadata)
                
                # Check for Gemini (Google AI) via XMP metadata
                if result["source"] == "Unknown":
                    gemini_info = ImageMetadataExtractor._detect_gemini(metadata)
                    if gemini_info:
                        result["source"] = gemini_info.get('source', 'Google Gemini')
                        result["parsed"]["parameters"]["generator"] = "Google Gemini"
                        if gemini_info.get('created'):
                            result["parsed"]["parameters"]["created"] = gemini_info['created']
                        result["parsed"]["prompt"] = "(AI-generated image - no prompt available)"
                
                # Check for ChatGPT/OpenAI via C2PA metadata
                if result["source"] == "Unknown":
                    chatgpt_info = ImageMetadataExtractor._detect_chatgpt(filepath)
                    if chatgpt_info:
                        result["source"] = chatgpt_info.get('source', 'ChatGPT / OpenAI')
                        result["parsed"]["parameters"]["generator"] = "OpenAI"
                        if chatgpt_info.get('model'):
                            result["parsed"]["parameters"]["model"] = chatgpt_info['model']
                        result["parsed"]["prompt"] = "(AI-generated image - no prompt available)"
                
                # Detect editing software (Photoshop, GIMP, etc.)
                editing_software = ImageMetadataExtractor._detect_editing_software(metadata, filepath)
                if editing_software:
                    result["parsed"]["parameters"]["editing_software"] = ", ".join(editing_software)
                    # Append to source if we have one
                    if result["source"] != "Unknown":
                        result["source"] = f"{result['source']} (edited with {', '.join(editing_software)})"
                    else:
                        result["source"] = f"Edited with {', '.join(editing_software)}"
                
                # Extract camera info, GPS, and other EXIF metadata
                camera_info = ImageMetadataExtractor._extract_camera_and_exif(metadata, img)
                if camera_info:
                    result["parsed"]["camera_info"] = camera_info
                    # If we detected a camera and source is still Unknown, set it as Camera photo
                    if result["source"] == "Unknown" and camera_info.get('camera'):
                        result["source"] = f"Camera: {camera_info['camera']}"
                
                # Check for any text data we can use
                if not result["parsed"].get("prompt"):
                    for key in ['parameters', 'Description', 'Comment', 'UserComment']:
                        if key in metadata and metadata[key]:
                            val = str(metadata[key])
                            if len(val) > 10:
                                result["parsed"]["prompt"] = val
                                break
                
        except Exception as e:
            result["error"] = str(e)
        
        return result
