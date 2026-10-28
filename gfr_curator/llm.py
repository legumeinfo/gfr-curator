import os
import json
import re
import sys
import time
from rich.console import Console
from rich.panel import Panel
import litellm

# Configure LiteLLM defaults
litellm.suppress_debug_info = True
litellm.drop_params = True

console = Console()
err_console = Console(stderr=True)

def normalize_model_name(model: str) -> str:
    """
    Normalizes model names to include provider prefixes if required by LiteLLM.
    e.g. 'gemini-flash-lite-latest' -> 'gemini/gemini-flash-lite-latest'
    """
    if not model:
        return model
    model = model.strip()
    if model.startswith("gemini-") and "/" not in model:
        return f"gemini/{model}"
    return model

def parse_llm_json_response(content: str):
    """
    Parses LLM response text into a list of gene record dictionaries.
    Handles JSON objects with array fields (e.g. {"genes": [...]}),
    raw JSON arrays, nested containers, and markdown code blocks.
    """
    if not content or not content.strip():
        raise ValueError("Received empty response from LLM.")
        
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        
    data = json.loads(text)

    def is_gene_dict(d):
        return isinstance(d, dict) and any(k in d for k in ("scientific_name", "gene_symbols", "gene_symbol_long", "traits"))

    records = []
    if isinstance(data, list):
        records = [item for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        for key in ("genes", "records", "data", "results", "gene_list", "extracted_genes", "gene_records"):
            if key in data:
                val = data[key]
                if isinstance(val, list):
                    records = [item for item in val if isinstance(item, dict)]
                    break
                elif isinstance(val, dict):
                    records = [item for item in val.values() if isinstance(item, dict)]
                    break

        if not records:
            if is_gene_dict(data):
                records = [data]
            else:
                for v in data.values():
                    if isinstance(v, list) and any(is_gene_dict(x) for x in v):
                        records = [x for x in v if isinstance(x, dict)]
                        break
                    elif is_gene_dict(v):
                        records.append(v)

    valid_records = [r for r in records if is_gene_dict(r)]
    if not valid_records:
        raise ValueError(f"LLM response did not contain valid gene records: {text[:200]}")
    return valid_records

def format_friendly_error(err) -> str:
    """Extracts a clean, human-readable error message from an LLM exception."""
    if not err:
        return "Unknown error"
    if isinstance(err, str):
        raw_msg = err
    else:
        raw_msg = getattr(err, "message", None) or str(err)

    # 1. Try to extract JSON embedded in the error string or error.body
    clean_detail = None
    body = getattr(err, "body", None)
    if isinstance(body, dict):
        err_dict = body.get("error") or body
        if isinstance(err_dict, dict) and "message" in err_dict:
            clean_detail = str(err_dict["message"]).strip()
        elif isinstance(err_dict, str):
            clean_detail = err_dict.strip()

    if not clean_detail:
        start = raw_msg.find("{")
        end = raw_msg.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_str = raw_msg[start:end+1]
            try:
                data = json.loads(json_str)
                if isinstance(data, dict):
                    err_dict = data.get("error") or data
                    if isinstance(err_dict, dict) and "message" in err_dict:
                        clean_detail = str(err_dict["message"]).strip()
                    elif isinstance(err_dict, str):
                        clean_detail = err_dict.strip()
            except Exception:
                pass

    if clean_detail:
        return " ".join(clean_detail.split())

    status_code = getattr(err, "status_code", None)
    err_type_name = type(err).__name__

    # 2. Check for recognized exception types if no JSON detail found
    if "AuthenticationError" in err_type_name or status_code in (401, 403):
        return "Authentication failed. Please verify your API key."
    if "NotFoundError" in err_type_name or status_code == 404:
        return "Model not found or is no longer available."
    if "ServiceUnavailableError" in err_type_name or status_code == 503:
        return "The model provider is temporarily unavailable or experiencing high demand."
    if "RateLimitError" in err_type_name or status_code == 429:
        return "Rate limit or quota exceeded. Please try again later."
    if "APIConnectionError" in err_type_name or "Timeout" in err_type_name:
        return "Connection failed or timed out. Please check your network connection."

    # 3. Strip technical prefixes from the raw string
    cleaned = raw_msg
    cleaned = re.sub(r"^(?:litellm\.|openai\.|anthropic\.)?[A-Za-z0-9_]+(?:Error|Exception):\s*", "", cleaned)
    cleaned = re.sub(r"^[A-Za-z0-9_]+Exception\s*-\s*", "", cleaned)
    return " ".join(cleaned.strip().split())

def query_llm(abstract: str, api_key: str = None, model: str = None, full_text: str = None, debug: bool = False):
    """
    Queries LLM to extract gene function information from a scientific paper abstract
    and optional full-text excerpts. Supports automatic retries and fallback models.
    """
    paper_content = f"Scientific Paper Abstract:\n{abstract}"
    if full_text:
        # Cap full text to ~15,000 chars to avoid prompt overflow while providing crucial body details
        capped_body = full_text[:15000] if len(full_text) > 15000 else full_text
        paper_content += f"\n\nAdditional Open-Access Full-Text Excerpts:\n{capped_body}"

    prompt = f"""You are an expert biocurator for the Legume Information System (LIS). Your task is to extract gene function information from the provided scientific paper text and output a structured JSON object matching the LIS Gene Function Registry schema.

{paper_content}

Please extract the following information and output it as a valid JSON object with a "genes" array containing one object for EACH distinct gene characterized in the paper:

{{
  "genes": [
    {{
      "scientific_name": "scientific name of the plant species studied, e.g. Glycine max",
      "classical_locus": "any classical locus name if mentioned, otherwise null",
      "gene_symbols": ["list of gene symbols for THIS specific gene, e.g. GmCIF1"],
      "gene_symbol_long": "the long-hand version of the main gene symbol acronym, e.g. Cell Wall Invertase Inhibitor 1",
      "gene_model_pub_name": "the gene model name as listed in the publication (e.g., Glyma02g17170 or Glyma.17G036300)",
      "confidence": "an integer from 2 to 5 showing how strong the evidence is:
                    5 - High confidence (gene functional validation with stable transgenic lines)
                    4 - Medium-High (functional validation with transient expression, e.g. RNAi transient or VIGS, or heterologous expression with strong in vitro proof)
                    3 - Medium (in vitro enzyme activity only, or genetic mapping with tight linkage)
                    2 - Medium-Low (gene expression correlates with trait, or mutant phenotype described in other species only)",
      "comments": ["list of 1-3 comments briefly describing THIS gene's function, regulation, and interactors"],
      "phenotype_synopsis": "brief synopsis of the phenotype for THIS gene",
      "traits": ["list of key trait keywords to lookup for THIS gene, e.g. ['seed weight', 'sucrose metabolism']"],
      "curation_notes": "brief notes on evidence from the text supporting this gene model, confidence score, and traits"
    }}
  ]
}}

Make sure your response contains ONLY valid JSON without markdown formatting or any extra conversational text.
"""
    env_model = os.environ.get("LLM_MODEL") or os.environ.get("GFR_MODEL") or os.environ.get("GEMINI_MODEL")
    target_model = normalize_model_name(model or env_model)

    if not target_model:
        err_console.print("\n[bold red][!] Error: No LLM model configured.[/bold red]")
        err_console.print("[dim]Please specify a model with --model or run: [cyan]gfr-curate --configure[/cyan][/dim]\n")
        sys.exit(1)

    if debug:
        console.print(Panel(
            f"[bold]Target Model:[/bold] {target_model}\n"
            f"[bold]Abstract Size:[/bold] {len(abstract):,} chars\n"
            f"[bold]Full Text Excerpt Size:[/bold] {len(capped_body) if full_text else 0:,} chars\n"
            f"[bold]Total Prompt Size:[/bold] {len(prompt):,} chars",
            title="[bold yellow]Debug: LLM Prompt Context[/bold yellow]",
            border_style="yellow",
            expand=False
        ))

    # Set provider-specific env var if needed for LiteLLM
    if api_key:
        if target_model.startswith("openrouter/") or api_key.startswith("sk-or-"):
            if not os.environ.get("OPENROUTER_API_KEY"):
                os.environ["OPENROUTER_API_KEY"] = api_key

    last_error = None
    print(f"[*] Contacting LLM ({target_model})...")
    max_retries = 2
    for attempt in range(max_retries):
        try:
            kwargs = {
                "model": target_model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "timeout": 60,
            }
            if api_key:
                kwargs["api_key"] = api_key

            t0 = time.time()
            response = litellm.completion(**kwargs)
            elapsed = time.time() - t0

            first_choice = response.choices[0] if getattr(response, "choices", None) else None
            msg = getattr(first_choice, "message", None) if first_choice else None
            content = getattr(msg, "content", "") if msg else ""

            if debug:
                usage = getattr(response, "usage", None)
                usage_info = ""
                if usage:
                    prompt_toks = getattr(usage, "prompt_tokens", None)
                    comp_toks = getattr(usage, "completion_tokens", None)
                    tot_toks = getattr(usage, "total_tokens", None)
                    details = getattr(usage, "completion_tokens_details", None)
                    reasoning_toks = getattr(details, "reasoning_tokens", None) if details else None
                    usage_info = f" | Tokens: prompt={prompt_toks}, completion={comp_toks}, total={tot_toks}"
                    if reasoning_toks:
                        usage_info += f", reasoning={reasoning_toks}"
                console.print(f"[dim yellow][DEBUG] LLM response received in {elapsed:.2f}s{usage_info}[/dim yellow]")

                # Inspect for native reasoning tokens (DeepSeek-R1, Gemini Thinking, Claude, o1/o3)
                native_reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "thought", None)
                if isinstance(native_reasoning, str) and native_reasoning.strip():
                    console.print(Panel(
                        native_reasoning.strip(),
                        title="[bold cyan]Debug: Model Reasoning Output[/bold cyan]",
                        border_style="cyan",
                        expand=False
                    ))

                # Show response text preview
                raw_preview = content.strip()
                if len(raw_preview) > 800:
                    raw_preview = raw_preview[:800] + "\n... [truncated preview]"
                console.print(Panel(
                    raw_preview,
                    title="[bold yellow]Debug: Raw JSON Response[/bold yellow]",
                    border_style="yellow",
                    expand=False
                ))

            parsed = parse_llm_json_response(content)
            if debug:
                console.print(f"[dim yellow][DEBUG] Successfully parsed {len(parsed)} gene record(s) from LLM output.[/dim yellow]")
            return parsed
        except Exception as e:
            last_error = e
            friendly_err = format_friendly_error(e)
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                err_console.print(f"[bold yellow][-] LLM error ({target_model}): {friendly_err}. Retrying in {wait_time}s...[/bold yellow]")
                time.sleep(wait_time)

    friendly_last = format_friendly_error(last_error) if last_error else "Request failed"
    err_console.print(f"\n[bold red][!] Error: LLM request failed for {target_model}:[/bold red] {friendly_last}")
    err_console.print("[dim]Tip: You can reconfigure your model anytime with: [cyan]gfr-curate --configure[/cyan][/dim]\n")
    sys.exit(1)

def query_gemini_api(api_key, abstract, model_override=None, debug: bool = False):
    """
    Backwards-compatible wrapper calling query_llm.
    """
    return query_llm(abstract=abstract, api_key=api_key, model=model_override or "gemini/gemini-flash-lite-latest", debug=debug)

