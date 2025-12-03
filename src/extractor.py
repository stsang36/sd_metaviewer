"""
Image metadata extraction utilities.
"""

import json
import os
import re
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
