import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

console = Console()

def get_config_dir() -> Path:
    """Returns the user configuration directory path."""
    if os.environ.get("GFR_CONFIG_DIR"):
        return Path(os.environ["GFR_CONFIG_DIR"])
    return Path.home() / ".config" / "gfr-curator"

def get_config_file() -> Path:
    """Returns the user configuration file path."""
    if os.environ.get("GFR_CONFIG_FILE"):
        return Path(os.environ["GFR_CONFIG_FILE"])
    return get_config_dir() / "config.env"

def is_local_model(model: str) -> bool:
    """Checks whether the specified model is a local model not requiring an API key."""
    if not model:
        return False
    m = model.lower()
    return m.startswith("ollama") or m.startswith("local") or "localhost" in m

def get_provider_info(model: str):
    """
    Returns (provider_name, default_env_var, signup_url)
    """
    if not model:
        return ("Gemini", "GEMINI_API_KEY", "https://aistudio.google.com/")
    m = model.lower()
    if "openrouter" in m:
        return ("OpenRouter", "OPENROUTER_API_KEY", "https://openrouter.ai/keys")
    if "gpt" in m or "openai" in m or m.startswith("o1") or m.startswith("o3"):
        return ("OpenAI", "OPENAI_API_KEY", "https://platform.openai.com/api-keys")
    if "claude" in m or "anthropic" in m:
        return ("Anthropic", "ANTHROPIC_API_KEY", "https://console.anthropic.com/")
    if "groq" in m:
        return ("Groq", "GROQ_API_KEY", "https://console.groq.com/keys")
    if "mistral" in m:
        return ("Mistral", "MISTRAL_API_KEY", "https://console.mistral.ai/")
    if "deepseek" in m:
        return ("DeepSeek", "DEEPSEEK_API_KEY", "https://platform.deepseek.com/")
    if "gemini" in m:
        return ("Gemini", "GEMINI_API_KEY", "https://aistudio.google.com/")
    return (f"LLM ({model})", "LLM_API_KEY", "")

def mask_key(key: str) -> str:
    """Masks an API key for safe display in console."""
    if not key:
        return "(none)"
    if len(key) <= 8:
        return "********"
    return f"{key[:4]}...{key[-4:]}"

def read_config_dict() -> dict:
    """Reads key-value pairs from the user configuration file."""
    config_file = get_config_file()
    if not config_file.exists():
        return {}
    res = {}
    with open(config_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                res[k.strip()] = v.strip().strip("'\"")
    return res

def save_config_dict(updates: dict) -> Path:
    """
    Saves or updates configuration in the user config file with 0600 permissions.
    Preserves other previously configured keys.
    """
    config_dir = get_config_dir()
    config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    
    current = read_config_dict()
    current.update({k: v for k, v in updates.items() if v is not None})
    
    config_file = get_config_file()
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(config_file, flags, 0o600)
    with open(fd, "w", encoding="utf-8") as f:
        f.write("# LIS Gene Function Registry (gfr-curator) Configuration\n")
        f.write("# Managed automatically by `gfr-curate --configure`\n\n")
        for k, v in current.items():
            f.write(f"{k}={v}\n")
            
    # Update current process environment
    for k, v in current.items():
        os.environ[k] = v
        
    return config_file

def load_user_config():
    """
    Loads user config from ~/.config/gfr-curator/config.env first,
    and then also allows local .env in working directory to override.
    """
    config_file = get_config_file()
    if config_file.exists():
        load_dotenv(config_file)
    # Also load local .env if present
    load_dotenv()

def is_configured() -> bool:
    """
    Checks if the tool has been configured previously.
    """
    config_file = get_config_file()
    if not config_file.exists():
        return False
    data = read_config_dict()
    return bool(data.get("LLM_MODEL") or any(k.endswith("_KEY") for k in data))

def _litellm_model_registry() -> dict:
    """
    Returns LiteLLM's model registry: the copy bundled with the installed package, overlaid
    with litellm.model_cost. The bundled copy is always read because litellm.model_cost may be
    replaced at import time by a remote map that omits some providers (e.g. OpenRouter).
    """
    registry = {}
    try:
        from importlib.resources import files
        bundled = files("litellm") / "model_prices_and_context_window_backup.json"
        registry.update(json.loads(bundled.read_text(encoding="utf-8")))
    except Exception:
        pass
    try:
        import litellm
        registry.update(getattr(litellm, "model_cost", {}) or {})
    except Exception:
        pass
    registry.pop("sample_spec", None)
    return registry

def _registry_models(provider: str) -> list:
    """Returns chat model names for a provider from LiteLLM's registry."""
    return [
        name for name, meta in _litellm_model_registry().items()
        if isinstance(meta, dict)
        and meta.get("litellm_provider") == provider
        and meta.get("mode", "chat") == "chat"
    ]

def get_local_ollama_models(timeout: float = 0.5) -> list:
    """
    Returns models installed in the local Ollama server (via its /api/tags endpoint),
    formatted as 'ollama/<name>'. Returns [] if Ollama is not running.
    """
    base = (os.environ.get("OLLAMA_API_BASE") or "http://localhost:11434").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    models = []
    for item in data.get("models", []):
        name = item.get("name") or item.get("model")
        if name:
            models.append(f"ollama/{name.removesuffix(':latest')}")
    return models

def _read_openrouter_cache(cache_file: Path, max_age: float = None) -> list:
    """Returns cached OpenRouter models, or [] if missing, invalid, or older than max_age seconds."""
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)
        if not isinstance(cached, dict):
            return []
        if max_age is not None and time.time() - cached.get("timestamp", 0) >= max_age:
            return []
        models = cached.get("models")
        return models if isinstance(models, list) else []
    except Exception:
        return []

def get_openrouter_models(timeout: float = 1.5) -> list:
    """
    Returns a list of OpenRouter chat models, in order of preference:
    a fresh local cache, the live OpenRouter API, an expired cache, then the
    registry bundled with LiteLLM.
    """
    cache_file = get_config_dir() / "openrouter_models.json"
    cache_ttl = 7 * 86400  # 7 days

    models = _read_openrouter_cache(cache_file, max_age=cache_ttl)
    if models:
        return models

    # Try fetching dynamically from OpenRouter public API
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"User-Agent": "gfr-curator"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        models = []
        for item in data.get("data", []):
            m_id = item.get("id")
            if not m_id:
                continue
            endpoints = item.get("endpoints") or []
            if endpoints and "/api/v1/chat/completions" not in endpoints:
                continue
            formatted = m_id if m_id.startswith("openrouter/") else f"openrouter/{m_id}"
            models.append(formatted)

        if models:
            try:
                get_config_dir().mkdir(mode=0o700, parents=True, exist_ok=True)
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump({"timestamp": time.time(), "models": models}, f)
            except Exception:
                pass
            return models
    except Exception:
        pass

    return _read_openrouter_cache(cache_file) or _registry_models("openrouter")

def get_all_known_models() -> list:
    """
    Returns a deduplicated list of chat models dynamically pulled from LiteLLM's registry,
    prioritizing primary providers (Gemini, OpenAI, Anthropic, DeepSeek, Groq, Mistral, Ollama, OpenRouter).
    """
    seen = set()
    models = []

    primary_providers = [
        "gemini",
        "openai",
        "anthropic",
        "deepseek",
        "groq",
        "mistral",
        "ollama",
        "openrouter",
    ]

    excluded_keywords = (
        "ft:", "embed", "whisper", "tts", "dall-e", "imagen", "image",
        "moderation", "guard", "babbage", "davinci", "curie", "ada",
        "1024-x-", "1536-x-", "video", "audio", "transcribe", "translate",
        "robotics", "computer-use", "realtime", "live-preview", "live-translate",
    )

    def is_desirable_chat(name: str, meta: dict = None) -> bool:
        nl = name.lower()
        if any(kw in nl for kw in excluded_keywords):
            return False
        if meta and isinstance(meta, dict):
            mode = meta.get("mode")
            if mode and mode != "chat":
                return False
        return True

    def model_sort_key(name: str):
        nl = name.lower()
        is_flagship = any(k in nl for k in (
            "4o", "flash", "pro", "sonnet", "haiku", "opus", "chat",
            "reasoner", "r1", "codestral", "large", "small", "o1", "o3", "latest"
        ))
        return (0 if is_flagship else 1, name)

    cost_dict = _litellm_model_registry()
    try:
        import litellm
        models_by_prov = getattr(litellm, "models_by_provider", {})
        model_list = getattr(litellm, "model_list", [])
    except Exception:
        models_by_prov, model_list = {}, []

    def add(name: str, bucket: list):
        if name not in seen:
            seen.add(name)
            bucket.append(name)

    # 1. Primary provider chat models
    for prov in primary_providers:
        prov_models = []
        for name, meta in cost_dict.items():
            if not isinstance(meta, dict):
                continue
            if meta.get("litellm_provider", "").lower() == prov and is_desirable_chat(name, meta):
                add(f"gemini/{name}" if prov == "gemini" and not name.startswith("gemini/") else name, prov_models)

        for name in models_by_prov.get(prov, set()):
            if is_desirable_chat(name):
                add(f"gemini/{name}" if prov == "gemini" and not name.startswith("gemini/") else name, prov_models)

        if prov == "openrouter":
            for om in get_openrouter_models():
                if is_desirable_chat(om):
                    add(om, prov_models)

        prov_models.sort(key=model_sort_key)

        # Models actually installed in the local Ollama server go first
        if prov == "ollama":
            installed = []
            for om in get_local_ollama_models():
                if om in seen:
                    prov_models.remove(om)
                else:
                    seen.add(om)
                installed.append(om)
            prov_models = installed + prov_models

        models.extend(prov_models)

    # 2. Other chat models in the registry
    other_chat = []
    for name, meta in cost_dict.items():
        if isinstance(meta, dict) and meta.get("mode") == "chat" and is_desirable_chat(name, meta):
            if not name.startswith("bedrock/") and not name.startswith("sagemaker/"):
                add(name, other_chat)
    other_chat.sort(key=model_sort_key)
    models.extend(other_chat)

    # 3. Any remaining models from litellm.model_list
    other_general = []
    for name in model_list:
        if is_desirable_chat(name) and not name.startswith("bedrock/") and not name.startswith("sagemaker/"):
            add(name, other_general)
    other_general.sort()
    models.extend(other_general)

    return models

try:
    from prompt_toolkit.completion import Completer, Completion
except ImportError:
    class Completer:
        pass
    class Completion:
        def __init__(self, text, start_position=0):
            self.text = text
            self.start_position = start_position

class ModelCompleter(Completer):
    """Completer for model names supporting prefix, substring, and token matching."""
    def __init__(self, models: list):
        self.models = models

    def get_completions(self, document, complete_event):
        import re

        query = document.text_before_cursor.strip().lower()
        if not query:
            for m in self.models[:20]:
                yield Completion(m, start_position=-len(document.text_before_cursor))
            return

        tokens = query.split()
        seen = set()
        count = 0

        # Tier 1: exact substring match
        for m in self.models:
            m_lower = m.lower()
            if query in m_lower:
                seen.add(m)
                yield Completion(m, start_position=-len(document.text_before_cursor))
                count += 1
                if count >= 25:
                    return

        # Tier 2: all tokens match
        for m in self.models:
            if m in seen:
                continue
            m_lower = m.lower()
            if all(t in m_lower for t in tokens):
                seen.add(m)
                yield Completion(m, start_position=-len(document.text_before_cursor))
                count += 1
                if count >= 25:
                    return

        # Tier 3: fuzzy subsequence
        fuzzy_pat = ".*?".join(re.escape(c) for c in query if not c.isspace())
        for m in self.models:
            if m in seen:
                continue
            if re.search(fuzzy_pat, m, re.IGNORECASE):
                seen.add(m)
                yield Completion(m, start_position=-len(document.text_before_cursor))
                count += 1
                if count >= 25:
                    return

def _prompt_toolkit_select(all_models: list, initial_query: str = "", current_model: str = "") -> str:
    """Invokes prompt_toolkit interactive prompt with live dropdown completion."""
    from prompt_toolkit.shortcuts import prompt as pt_prompt, CompleteStyle
    from prompt_toolkit.styles import Style
    from prompt_toolkit.key_binding import KeyBindings

    kb = KeyBindings()

    @kb.add("down")
    def _(event):
        b = event.current_buffer
        if b.complete_state:
            b.complete_next()
        else:
            b.start_completion(select_first=True)

    @kb.add("up")
    def _(event):
        b = event.current_buffer
        if b.complete_state:
            b.complete_previous()

    @kb.add("tab")
    def _(event):
        b = event.current_buffer
        if b.complete_state:
            b.complete_next()
        else:
            b.start_completion(select_first=True)

    @kb.add("s-tab")
    def _(event):
        b = event.current_buffer
        if b.complete_state:
            b.complete_previous()

    @kb.add("enter")
    def _(event):
        b = event.current_buffer
        if b.complete_state and b.complete_state.current_completion:
            b.apply_completion(b.complete_state.current_completion)
        b.validate_and_handle()

    pt_style = Style.from_dict({
        "prompt": "ansicyan bold",
        "completion-menu": "bg:#262626 #e5e5e5",
        "completion-menu.completion": "bg:#262626 #e5e5e5",
        "completion-menu.completion.current": "bg:#0284c7 #ffffff bold",
        "scrollbar.background": "bg:#171717",
        "scrollbar.button": "bg:#525252",
    })

    completer = ModelCompleter(all_models)
    prompt_str = f"Search model (default: {current_model}): " if current_model else "Search model: "

    return pt_prompt(
        prompt_str,
        default=initial_query,
        completer=completer,
        complete_while_typing=True,
        complete_style=CompleteStyle.COLUMN,
        reserve_space_for_menu=8,
        key_bindings=kb,
        style=pt_style,
    ).strip()

def search_and_select_model(current_model="gemini/gemini-flash-lite-latest", out_console=None, initial_query="") -> str:
    """
    Interactive live dropdown search for selecting any model.
    """
    c = out_console or console
    all_models = get_all_known_models()
    if current_model:
        if current_model in all_models:
            all_models.remove(current_model)
        all_models.insert(0, current_model)

    if sys.stdin.isatty():
        try:
            selected = _prompt_toolkit_select(all_models, initial_query=initial_query, current_model=current_model)
            if not selected:
                return current_model

            if selected not in all_models:
                confirm = c.input(f"Use unlisted model '{selected}'? [Y/n]: ").strip().lower()
                if confirm in ("", "y", "yes"):
                    return selected
                return current_model

            return selected

        except (KeyboardInterrupt, EOFError):
            raise
        except Exception as e:
            c.print(f"[dim](Interactive dropdown unavailable: {e})[/dim]")

    # Non-interactive fallback
    try:
        prompt_str = f"Search model (default: {current_model}): " if current_model else "Search model: "
        query = c.input(prompt_str).strip()
        return query if query else current_model
    except (KeyboardInterrupt, EOFError):
        raise

def prompt_masked_key(prompt_text: str, out_console=None) -> str:
    """
    Prompts for an API key with masked asterisk (*) feedback as the user types.
    """
    c = out_console or console
    if sys.stdin.isatty():
        try:
            from prompt_toolkit.shortcuts import prompt as pt_prompt
            return pt_prompt(prompt_text, is_password=True).strip()
        except (KeyboardInterrupt, EOFError):
            raise
        except Exception:
            pass
    return c.input(prompt_text, password=True).strip()

def run_configurator(out_console=None, is_initial=False):
    """
    Interactive configurator for default model and API key.
    """
    c = out_console or console
    current_cfg = read_config_dict()
    current_model = current_cfg.get("LLM_MODEL") or os.environ.get("LLM_MODEL") or "gemini/gemini-flash-lite-latest"

    if is_initial:
        c.print("\n[bold]Configure default model and API key:[/bold]")
    else:
        c.print(f"\n[bold]Current model:[/bold] [cyan]{current_model}[/cyan]")
        stored_keys = [f"{k}: {mask_key(v)}" for k, v in current_cfg.items() if "KEY" in k]
        if stored_keys:
            c.print(f"[dim]Keys: {', '.join(stored_keys)}[/dim]")
        c.print()

    # 1. Model Selection
    c.print("[bold]Select model:[/bold] [dim](type to search, ↑/↓ to navigate, Enter to select)[/dim]")
    try:
        chosen_model = search_and_select_model(current_model=current_model, out_console=c)
    except (KeyboardInterrupt, EOFError):
        c.print("\nCancelled.")
        sys.exit(1)

    if not chosen_model:
        chosen_model = current_model or "gemini/gemini-flash-lite-latest"

    c.print(f"[green]Selected: {chosen_model}[/green]\n")

    # 2. API Key Selection
    updates = {"LLM_MODEL": chosen_model}

    if is_local_model(chosen_model):
        c.print("[green]Local model — no API key required.[/green]")
    else:
        provider_name, env_var, url = get_provider_info(chosen_model)
        existing_key = current_cfg.get(env_var) or os.environ.get(env_var)

        if existing_key:
            c.print(f"Existing key: [dim]{mask_key(existing_key)}[/dim]")
            try:
                new_key = prompt_masked_key(f"New {provider_name} key (Enter to keep): ", out_console=c)
            except (KeyboardInterrupt, EOFError):
                c.print("\nCancelled.")
                sys.exit(1)
            final_key = new_key if new_key else existing_key
        else:
            if url:
                c.print(f"[dim]Key URL: {url}[/dim]")
            try:
                new_key = prompt_masked_key(f"{provider_name} API key ({env_var}): ", out_console=c)
            except (KeyboardInterrupt, EOFError):
                c.print("\nCancelled.")
                sys.exit(1)
            final_key = new_key

        if final_key:
            updates[env_var] = final_key
        else:
            c.print(f"[yellow]No key provided for {chosen_model}. You will be prompted at runtime.[/yellow]")

    # Save to config file
    saved_path = save_config_dict(updates)
    c.print(f"\n[bold green]Saved configuration to {saved_path}[/bold green]\n")

