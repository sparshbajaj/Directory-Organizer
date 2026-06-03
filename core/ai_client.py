import json
import os
import time
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from urllib import request, error

from core.ai_renamer import sanitize_filename, read_text_excerpt, DEFAULT_MAX_LENGTH


DEFAULT_PAGE_CHARS = 2000
DEFAULT_MAX_PAGES = 2
DEFAULT_MAX_SNIPPET_CHARS = DEFAULT_PAGE_CHARS * DEFAULT_MAX_PAGES


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
    api_key: str = ""
    temperature: float = 0.2
    max_tokens: int = 48
    timeout: int = 20
    consent: bool = False
    send_content: bool = False
    max_snippet_chars: int = DEFAULT_MAX_SNIPPET_CHARS
    max_pages: int = DEFAULT_MAX_PAGES

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


class AIClient:
    def __init__(self, config: AIProviderConfig, cache: Optional[AINameCache] = None):
        self.config = config
        self.cache = cache

    def build_cache_key(self, file_path: Path) -> str:
        try:
            stat = file_path.stat()
            size = stat.st_size
            mtime = stat.st_mtime_ns
        except OSError:
            size = 0
            mtime = 0
        base = "|".join(
            [
                str(file_path),
                str(size),
                str(mtime),
                self.config.provider,
                self.config.resolved_model(),
                self.config.resolved_base_url(),
                str(self.config.temperature),
                str(self.config.max_tokens),
            ]
        )
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def build_prompt(self, file_path: Path, snippet: str) -> Tuple[str, str]:
        ext = file_path.suffix.lower()
        size = file_path.stat().st_size if file_path.exists() else 0
        system = (
            "You are a file renaming assistant. "
            "Return a concise, descriptive filename without the extension. "
            f"Limit to {DEFAULT_MAX_LENGTH} characters. "
            "Do not include quotes or extra commentary."
        )
        user_lines = [
            f"Filename: {file_path.name}",
            f"Extension: {ext or 'none'}",
            f"Size bytes: {size}",
        ]
        if snippet:
            user_lines.append("Content snippet:")
            user_lines.append(snippet)
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

    def suggest_name(self, file_path: Path) -> Tuple[Optional[str], Dict[str, Any]]:
        if self.config.provider == "local":
            return None, {}
        if not self.config.consent:
            return None, {}
        api_key = self.config.resolved_api_key()
        if not api_key:
            return None, {}
        base_url = self.config.resolved_base_url().rstrip("/")
        model = self.config.resolved_model()
        if not base_url or not model:
            return None, {}

        snippet = ""
        if self.config.send_content:
            snippet = read_text_excerpt(
                file_path,
                max_chars=self.config.max_snippet_chars,
                max_pages=self.config.max_pages,
            )

        cache_key = self.build_cache_key(file_path)
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached:
                return cached, self.data_sent_summary(file_path, snippet)

        system, user = self.build_prompt(file_path, snippet)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        auth_prefix = "Bearer "
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"{auth_prefix}{api_key}",
        }
        req = request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        retry = 0
        while True:
            try:
                with request.urlopen(req, timeout=self.config.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except error.HTTPError as e:
                if e.code == 429 and retry < 3:
                    retry_after = e.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else 2 ** retry
                    time.sleep(wait)
                    retry += 1
                    continue
                return None, self.data_sent_summary(file_path, snippet)
            except error.URLError:
                return None, self.data_sent_summary(file_path, snippet)

        content = ""
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None, self.data_sent_summary(file_path, snippet)

        cleaned = sanitize_filename(content.strip().strip('"').strip("'"))
        if not cleaned:
            return None, self.data_sent_summary(file_path, snippet)

        if self.cache:
            self.cache.set(cache_key, cleaned)
            self.cache.save()

        return cleaned, self.data_sent_summary(file_path, snippet)
