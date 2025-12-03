"""
Metadata parsers for various AI image generation tools.
"""

import json
import re
from typing import Dict, Any


class MetadataParser:
    """Parses metadata from various AI image generation tools."""
    
    @staticmethod
    def parse_auto1111(params: str) -> Dict[str, Any]:
        """Parse AUTOMATIC1111 WebUI format metadata."""
        result = {
            "prompt": "",
            "negative_prompt": "",
            "parameters": {}
        }
        
        try:
            # Split by "Negative prompt:" if exists
            if "Negative prompt:" in params:
                parts = params.split("Negative prompt:", 1)
                result["prompt"] = parts[0].strip()
                remaining = parts[1]
            else:
                remaining = params
                # Try to find where parameters start
                param_match = re.search(r'\n(Steps:|Size:|Seed:|Model:|Sampler:)', remaining)
                if param_match:
                    result["prompt"] = remaining[:param_match.start()].strip()
                    remaining = remaining[param_match.start():]
                else:
                    result["prompt"] = remaining.strip()
                    return result
            
            # Find where the generation parameters start
            param_patterns = [
                r'Steps:\s*(\d+)',
                r'Sampler:\s*([^,\n]+)',
                r'CFG scale:\s*([\d.]+)',
                r'Seed:\s*(\d+)',
                r'Size:\s*(\d+x\d+)',
                r'Model hash:\s*([a-fA-F0-9]+)',
                r'Model:\s*([^,\n]+)',
                r'Denoising strength:\s*([\d.]+)',
                r'Clip skip:\s*(\d+)',
                r'ENSD:\s*(\d+)',
                r'Hires upscale:\s*([\d.]+)',
                r'Hires steps:\s*(\d+)',
                r'Hires upscaler:\s*([^,\n]+)',
            ]
            
            # Extract negative prompt (everything before the first parameter)
            first_param_pos = len(remaining)
            for pattern in param_patterns:
                match = re.search(pattern, remaining)
                if match and match.start() < first_param_pos:
                    first_param_pos = match.start()
            
            if first_param_pos > 0:
                result["negative_prompt"] = remaining[:first_param_pos].strip().strip(',').strip()
            
            # Extract parameters
            param_section = remaining[first_param_pos:]
            for pattern in param_patterns:
                match = re.search(pattern, param_section)
                if match:
                    key = pattern.split(r':\s*')[0].replace(r'\\', '')
                    result["parameters"][key] = match.group(1).strip()
            
        except Exception:
            result["prompt"] = params
        
        return result
    
    @staticmethod
    def parse_comfyui(workflow) -> Dict[str, Any]:
        """Parse ComfyUI workflow JSON."""
        result = {
            "prompt": "",
            "negative_prompt": "",
            "parameters": {},
            "workflow": None,
            "models": [],
            "loras": []
        }
        
        try:
            if isinstance(workflow, str):
                data = json.loads(workflow)
            else:
                data = workflow
            result["workflow"] = data
            
            if not isinstance(data, dict):
                return result
            
            prompts = []
            negative_prompts = []
            
            # Look for common node types
            for node_id, node in data.items():
                if not isinstance(node, dict):
                    continue
                    
                class_type = node.get("class_type", "")
                inputs = node.get("inputs", {})
                meta = node.get("_meta", {})
                title = meta.get("title", "").lower() if isinstance(meta, dict) else ""
                
                # Text encoding nodes (prompts)
                if class_type in ["CLIPTextEncode", "CLIPTextEncodeSDXL", "CLIPTextEncodeFlux"]:
                    text = inputs.get("text", "")
                    if text and isinstance(text, str):
                        # Check if it's negative based on title or node connections
                        if "negative" in title or "neg" in title:
                            negative_prompts.append(text)
                        else:
                            prompts.append(text)
                
                # ConditioningZeroOut typically used for negative/empty conditioning
                if class_type == "ConditioningZeroOut":
                    result["parameters"]["empty_negative"] = "true"
                
                # KSampler nodes (generation parameters)
                if "KSampler" in class_type:
                    if inputs.get("steps"):
                        result["parameters"]["steps"] = str(inputs.get("steps"))
                    if inputs.get("cfg"):
                        result["parameters"]["cfg"] = str(inputs.get("cfg"))
                    if inputs.get("seed"):
                        result["parameters"]["seed"] = str(inputs.get("seed"))
                    if inputs.get("sampler_name"):
                        result["parameters"]["sampler"] = str(inputs.get("sampler_name"))
                    if inputs.get("scheduler"):
                        result["parameters"]["scheduler"] = str(inputs.get("scheduler"))
                    if inputs.get("denoise"):
                        result["parameters"]["denoise"] = str(inputs.get("denoise"))
                
                # Model loaders
                if class_type in ["CheckpointLoaderSimple", "CheckpointLoader", "UNETLoader"]:
                    model_name = inputs.get("ckpt_name") or inputs.get("unet_name", "")
                    if model_name:
                        result["models"].append(model_name)
                        result["parameters"]["model"] = model_name
                
                # LoRA loaders
                if "LoraLoader" in class_type:
                    lora_name = inputs.get("lora_name", "")
                    if lora_name:
                        result["loras"].append(lora_name)
                        strength = inputs.get("strength_model", inputs.get("strength", 1.0))
                        result["parameters"]["lora"] = f"{lora_name} ({strength})"
                
                # VAE loader
                if class_type == "VAELoader":
                    vae_name = inputs.get("vae_name", "")
                    if vae_name:
                        result["parameters"]["vae"] = vae_name
                
                # CLIP loader
                if class_type == "CLIPLoader":
                    clip_name = inputs.get("clip_name", "")
                    if clip_name:
                        result["parameters"]["clip"] = clip_name
                
                # Image size nodes
                if class_type in ["EmptyLatentImage", "EmptySD3LatentImage", "EmptySDXLLatentImage"]:
                    width = inputs.get("width", "")
                    height = inputs.get("height", "")
                    if width and height:
                        result["parameters"]["size"] = f"{width}x{height}"
                
                # SaveImage node - check for z-image or other prefixes
                if class_type == "SaveImage":
                    prefix = inputs.get("filename_prefix", "")
                    if prefix:
                        result["parameters"]["output_prefix"] = prefix
                
                # Model sampling adjustments (AuraFlow, etc.)
                if "ModelSampling" in class_type:
                    shift = inputs.get("shift")
                    if shift:
                        result["parameters"]["shift"] = str(shift)
            
            # Combine prompts
            if prompts:
                result["prompt"] = prompts[0]  # Primary prompt
                if len(prompts) > 1:
                    result["parameters"]["additional_prompts"] = str(len(prompts) - 1)
            
            if negative_prompts:
                result["negative_prompt"] = negative_prompts[0]
                        
        except json.JSONDecodeError:
            pass
        except Exception as e:
            result["parameters"]["parse_error"] = str(e)
        
        return result
    
    @staticmethod
    def parse_novelai(data: Dict) -> Dict[str, Any]:
        """Parse NovelAI metadata format."""
        result = {
            "prompt": "",
            "negative_prompt": "",
            "parameters": {}
        }
        
        try:
            comment = data.get("Comment", "{}")
            if isinstance(comment, str):
                comment = json.loads(comment)
            
            result["prompt"] = comment.get("prompt", data.get("Description", ""))
            result["negative_prompt"] = comment.get("uc", "")
            result["parameters"] = {
                "steps": comment.get("steps", ""),
                "scale": comment.get("scale", ""),
                "seed": comment.get("seed", ""),
                "sampler": comment.get("sampler", ""),
                "strength": comment.get("strength", ""),
                "noise": comment.get("noise", ""),
            }
        except Exception:
            pass
        
        return result
