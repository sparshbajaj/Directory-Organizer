import json
import os
import time
import hashlib
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from urllib import request, error
import base64

from core.ai_renamer import sanitize_filename, read_text_excerpt, DEFAULT_MAX_LENGTH


DEFAULT_PAGE_CHARS = 2000
DEFAULT_MAX_PAGES = 2
DEFAULT_MAX_SNIPPET_CHARS = DEFAULT_PAGE_CHARS * DEFAULT_MAX_PAGES

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
IMAGE_MAX_DIM = 768
IMAGE_JPEG_QUALITY = 60
IMAGE_MAX_BYTES = 900_000

AI_REJECT_PHRASES = [
    "as an ai",
    "i can't",
    "i cannot",
    "sorry",
    "paused",
    "i need to",
    "create a new file",
    "tool",
    "system",
    "assistant",
    "user",
    "instruction",
    "response",
]


PROVIDER_PRESETS = {
    "local": {"base_url": "", "model": ""},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "openai/gpt-4o-mini"},
    "custom": {"base_url": "", "model": ""},
}


@dataclass
class AIProviderConfig:
    provider: str = "local"
    base_url: str = ""
    model: str = ""
    vision_model: str = ""
    api_key: str = ""
    temperature: float = 0.2
    max_tokens: int = 48
    timeout: int = 20
    consent: bool = False
    send_content: bool = False
    max_snippet_chars: int = DEFAULT_MAX_SNIPPET_CHARS
    max_pages: int = DEFAULT_MAX_PAGES
    retries: int = 2
    retry_backoff: float = 0.6

    def resolved_base_url(self) -> str:
        preset = PROVIDER_PRESETS.get(self.provider, {})
        return self.base_url or preset.get("base_url", "")

    def resolved_model(self) -> str:
        preset = PROVIDER_PRESETS.get(self.provider, {})
        return self.model or preset.get("model", "")

    def resolved_api_key(self) -> str:
        if self.provider == "openai":
            env_key = os.getenv("OPENAI_API_KEY")
        elif self.provider == "openrouter":
            env_key = os.getenv("OPENROUTER_API_KEY")
        else:
            env_key = os.getenv("DIRECTORY_ORGANIZER_AI_KEY")
        return env_key or self.api_key or ""


class AINameCache:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self._data = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            self._data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.write_text(json.dumps(self._data, indent=2))
        except OSError:
            pass

    def get(self, key: str) -> Optional[str]:
        entry = self._data.get(key)
        if not entry:
            return None
        return entry.get("name")

    def set(self, key: str, name: str) -> None:
        self._data[key] = {"name": name, "timestamp": time.time()}


def encode_image(image_path: Path) -> Optional[str]:
    try:
        from io import BytesIO
        try:
            from PIL import Image
        except Exception:
            return base64.b64encode(image_path.read_bytes()).decode("utf-8")

        with Image.open(image_path) as img:
            img.thumbnail((IMAGE_MAX_DIM, IMAGE_MAX_DIM))
            buffer = BytesIO()
            if img.mode not in {"RGB", "L"}:
                img = img.convert("RGB")
            img.save(buffer, format="JPEG", quality=IMAGE_JPEG_QUALITY, optimize=True)
            payload = buffer.getvalue()
            if len(payload) > IMAGE_MAX_BYTES:
                return None
            return base64.b64encode(payload).decode("utf-8")
    except Exception:
        return None


class AIClient:
    def __init__(self, config: AIProviderConfig, cache: Optional[AINameCache] = None):
        self.config = config
        self.cache = cache

    def build_cache_key(self, file_path: Path, model_override: Optional[str] = None) -> str:
        try:
            stat = file_path.stat()
            size = stat.st_size
            mtime = stat.st_mtime_ns
        except OSError:
            size = 0
            mtime = 0
        
        model = model_override or self.config.resolved_model()
        base = "|".join(
            [
                str(file_path),
                str(size),
                str(mtime),
                self.config.provider,
                model,
                self.config.resolved_base_url(),
                str(self.config.temperature),
                str(self.config.max_tokens),
            ]
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def build_prompt(self, file_path: Path, snippet: str) -> Tuple[str, str]:
        ext = file_path.suffix.lower()
        stat = file_path.stat() if file_path.exists() else None
        size = stat.st_size if stat else 0
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M") if stat else "unknown"
        
        system = (
            "You are a file renaming assistant. "
            "Return a concise, descriptive filename without the extension. "
            f"Limit to {DEFAULT_MAX_LENGTH} characters. "
            "Use metadata and content to be precise but short. "
            "Do not include quotes or extra commentary."
        )
        user_lines = [
            f"Filename: {file_path.name}",
            f"Extension: {ext or 'none'}",
            f"Folder: {file_path.parent.name}",
            f"Size bytes: {size}",
            f"Last modified: {mtime}",
        ]
        if snippet:
            user_lines.append("Content excerpt (short):")
            user_lines.append(snippet[:500]) # Keep it short as requested
        user = "\n".join(user_lines)
        return system, user

    def build_classification_prompt(self, file_path: Path, categories: List[str], snippet: str) -> Tuple[str, str]:
        ext = file_path.suffix.lower()
        stat = file_path.stat() if file_path.exists() else None
        size = stat.st_size if stat else 0
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M") if stat else "unknown"

        system = (
            "You are a file classification assistant. "
            "Suggest one of the provided categories for this file. "
            "Return ONLY the category name. If none fit, suggest a new one word category."
        )
        user_lines = [
            f"Filename: {file_path.name}",
            f"Extension: {ext or 'none'}",
            f"Size: {size} bytes",
            f"Modified: {mtime}",
            f"Available categories: {', '.join(categories)}",
        ]
        if snippet:
            user_lines.append("Content excerpt (short):")
            user_lines.append(snippet[:500])
        user = "\n".join(user_lines)
        return system, user

    def data_sent_summary(self, file_path: Path, snippet: str) -> Dict[str, Any]:
        size = file_path.stat().st_size if file_path.exists() else 0
        return {
            "filename": file_path.name,
            "extension": file_path.suffix.lower(),
            "size_bytes": size,
            "snippet_chars": len(snippet or ""),
        }

    def suggest_name(self, file_path: Path) -> Tuple[Optional[str], Dict[str, Any], str]:
        if self.config.provider == "local" or not self.config.consent:
            return None, {}, "disabled"
        
        api_key = self.config.resolved_api_key()
        if not api_key:
            return None, {}, "missing_api_key"
            
        base_url = self.config.resolved_base_url().rstrip("/")
        # Auto-select model based on file type
        is_image = file_path.suffix.lower() in IMAGE_EXTENSIONS
        model = self.config.vision_model if (is_image and self.config.vision_model) else self.config.resolved_model()
        
        if not base_url or not model:
            return None, {}, "missing_base_url_or_model"

        snippet = ""
        image_b64 = None
        if self.config.send_content:
            if is_image:
                image_b64 = encode_image(file_path)
            else:
                snippet = read_text_excerpt(
                    file_path,
                    max_chars=self.config.max_snippet_chars,
                    max_pages=self.config.max_pages,
                )

        cache_key = self.build_cache_key(file_path, model_override=model)
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached, self.data_sent_summary(file_path, snippet or (image_b64[:10] if image_b64 else "")), ""

        system, user = self.build_prompt(file_path, snippet)
        
        messages = [{"role": "system", "content": system}]
        if image_b64:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{file_path.suffix.lower().lstrip('.')};base64,{image_b64}"}
                    }
                ]
            })
        else:
            messages.append({"role": "user", "content": user})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        
        req = request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        last_error = ""
        attempts = max(self.config.retries, 0) + 1
        for attempt in range(attempts):
            try:
                with request.urlopen(req, timeout=self.config.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", []) if isinstance(data, dict) else []
                if not choices or "message" not in choices[0] or "content" not in choices[0]["message"]:
                    return None, self.data_sent_summary(file_path, snippet or (image_b64[:10] if image_b64 else "")), "bad_response"
                content = choices[0]["message"].get("content")
                if not content or not isinstance(content, str):
                    return None, self.data_sent_summary(file_path, snippet or (image_b64[:10] if image_b64 else "")), "bad_response:empty_content"
                cleaned = sanitize_filename(content.strip().strip('"').strip("'"))
                last_error = ""
                break
            except error.HTTPError as exc:
                try:
                    body = exc.read().decode("utf-8", errors="ignore")
                except Exception:
                    body = ""
                status = getattr(exc, "code", "unknown")
                detail = f"request_failed:HTTPError:{status}"
                if body:
                    detail = f"{detail}:{body[:500]}"
                last_error = detail
                if status in {408, 409, 425, 429, 500, 502, 503, 504} and attempt < attempts - 1:
                    time.sleep(self.config.retry_backoff * (attempt + 1))
                    continue
                return None, self.data_sent_summary(file_path, snippet or (image_b64[:10] if image_b64 else "")), detail
            except TimeoutError as exc:
                last_error = f"request_failed:TimeoutError:{exc}"
                if attempt < attempts - 1:
                    time.sleep(self.config.retry_backoff * (attempt + 1))
                    continue
                return None, self.data_sent_summary(file_path, snippet or (image_b64[:10] if image_b64 else "")), last_error
            except Exception as exc:
                message = str(exc) or type(exc).__name__
                last_error = f"request_failed:{type(exc).__name__}:{message}"
                return None, self.data_sent_summary(file_path, snippet or (image_b64[:10] if image_b64 else "")), last_error

        if not cleaned:
            return None, self.data_sent_summary(file_path, snippet or (image_b64[:10] if image_b64 else "")), "empty_response"

        if self._is_bad_ai_name(cleaned):
            return None, self.data_sent_summary(file_path, snippet or (image_b64[:10] if image_b64 else "")), "bad_ai_output"

        if self.cache:
            self.cache.set(cache_key, cleaned)
            self.cache.save()

        return cleaned, self.data_sent_summary(file_path, snippet or (image_b64[:10] if image_b64 else "")), ""

    def _is_bad_ai_name(self, name: str) -> bool:
        lowered = name.lower().strip()
        if not lowered:
            return True
        if len(lowered) > DEFAULT_MAX_LENGTH:
            return True
        if any(phrase in lowered for phrase in AI_REJECT_PHRASES):
            return True
        if "\n" in lowered or "\r" in lowered:
            return True
        return False

    def list_models(self) -> List[str]:
        api_key = self.config.resolved_api_key()
        base_url = self.config.resolved_base_url().rstrip("/")
        if not api_key or not base_url:
            return []

        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        req = request.Request(
            f"{base_url}/models",
            headers=headers,
            method="GET",
        )

        try:
            with request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            
            models = []
            if "data" in data:
                for m in data["data"]:
                    if isinstance(m, dict) and "id" in m:
                        models.append(m["id"])
                    elif isinstance(m, str):
                        models.append(m)
            return sorted(models)
        except Exception:
            return []

    def suggest_category(self, file_path: Path, categories: List[str]) -> Tuple[Optional[str], Dict[str, Any]]:
        if self.config.provider == "local" or not self.config.consent:
            return None, {}
        
        api_key = self.config.resolved_api_key()
        if not api_key:
            return None, {}
        
        base_url = self.config.resolved_base_url().rstrip("/")
        # Auto-select model based on file type
        is_image = file_path.suffix.lower() in IMAGE_EXTENSIONS
        model = self.config.vision_model if (is_image and self.config.vision_model) else self.config.resolved_model()
        
        if not base_url or not model:
            return None, {}

        snippet = ""
        image_b64 = None
        if self.config.send_content:
            if is_image:
                image_b64 = encode_image(file_path)
            else:
                snippet = read_text_excerpt(file_path)
            
        system, user = self.build_classification_prompt(file_path, categories, snippet)
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        
        messages = [{"role": "system", "content": system}]
        if image_b64:
            messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": user},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{file_path.suffix.lower().lstrip('.')};base64,{image_b64}"}
                    }
                ]
            })
        else:
            messages.append({"role": "user", "content": user})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 20,
        }
        
        req = request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        
        try:
            with request.urlopen(req, timeout=self.config.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"].strip()
            return content, self.data_sent_summary(file_path, snippet or (image_b64[:10] if image_b64 else ""))
        except Exception:
            return None, self.data_sent_summary(file_path, snippet or (image_b64[:10] if image_b64 else ""))
