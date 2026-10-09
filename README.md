# Gene Function Registry Curator (`gfr-curator`)

A command-line tool for curating records for the Legume Information System [Gene Function Registry](https://github.com/legumeinfo/gene-function-registry). Given a publication DOI, it fetches paper metadata and abstracts, extracts gene function annotations using an LLM, maps ontology terms, and generates schema-validated YAML drafts.

## Installation

Install with [`pipx`](https://pipx.pypa.io/) (recommended) or `pip`:

```bash
pipx install git+https://github.com/legumeinfo/gfr-curator.git
```

For local development:

```bash
git clone https://github.com/legumeinfo/gfr-curator.git
cd gfr-curator
pip install -e .
```

## Configuration

On first run, `gfr-curate` prompts you to choose a default model and enter its API key. Settings are saved to `~/.config/gfr-curator/config.env` with owner-only permissions (`0600`).

To update your model or API key:

```bash
gfr-curate --configure
```

You can also set API keys through environment variables (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `LLM_API_KEY`).

## Usage

### Curate a Paper

Pass a DOI directly:

```bash
gfr-curate 10.1093/jxb/erw425
```

Or run without arguments to enter the DOI interactively:

```bash
gfr-curate
```

Generated YAML files are saved to the current directory and validated against the GFR schema.

### Model Selection

Override your default model with `--model` (supports any [LiteLLM model](https://docs.litellm.ai/docs/providers)):

```bash
# OpenAI
gfr-curate 10.1093/jxb/erw425 --model gpt-4o

# Anthropic
gfr-curate 10.1093/jxb/erw425 --model claude-3-5-sonnet-20241022

# Local model via Ollama (no API key needed)
gfr-curate 10.1093/jxb/erw425 --model ollama/llama3

# Pass an API key directly
gfr-curate 10.1093/jxb/erw425 --model gpt-4o --key <api-key>
```

### Validate Records

Validate existing YAML records against `schema.json`:

```bash
gfr-validate path/to/record.yml
```

Or with a custom schema:

```bash
gfr-validate path/to/record.yml --schema path/to/schema.json
```

You can also validate through `gfr-curate`:

```bash
gfr-curate --validate path/to/record.yml
```

