# Gene Function Registry Curator (`gfr-curator`)

Command-line tool for curating records for the Legume Information System [Gene Function Registry](https://github.com/legumeinfo/gene-function-registry). Given a publication DOI, it retrieves paper metadata and full text, extracts gene function annotations using an LLM, resolves gene symbols to canonical LIS identifiers, maps ontology terms, and generates schema-validated YAML records.

## Installation

Install with [`pipx`](https://pipx.pypa.io/) or `pip`:

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

On first run, `gfr-curate` prompts you for a default model and API key. Settings are saved to `~/.config/gfr-curator/config.env` with owner-only permissions (`0600`).

To change your settings:

```bash
gfr-curate --configure
```

You can also set credentials via environment variables (`GEMINI_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `LLM_API_KEY`).

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

Draft YAML files are written to the current working directory and checked against `schema.json`.

### Legumista

`gfr-curate` utilizes the [Legumista](https://github.com/legumeinfo/legumista) MCP server (`https://mcp.legumeinfo.org`). This enables:
- Open-access paper text retrieval (`read_paper`)
- Gene symbol resolution to canonical LIS gene models across assemblies (`mine_gene_symbol`)
- Curated Gene Ontology term lookups (`mine_gene_ontology`)
- Post-curation identifier verification against LIS databases (`verify_ids`)

Use `--no-mcp` to disable MCP and run local direct API queries, or `--mcp-url` to target a local server:

```bash
# Curate using Legumista (default)
gfr-curate 10.1093/jxb/erw425

# Disable MCP and use direct API lookups
gfr-curate 10.1093/jxb/erw425 --no-mcp

# Point to a local Legumista instance
gfr-curate 10.1093/jxb/erw425 --mcp-url http://127.0.0.1:8000
```

### Model Selection

Override your configured model with `--model` (supports any [LiteLLM model](https://docs.litellm.ai/docs/providers)):

```bash
# OpenAI
gfr-curate 10.1093/jxb/erw425 --model gpt-4o

# Anthropic
gfr-curate 10.1093/jxb/erw425 --model claude-3-5-sonnet-20241022

# Local model via Ollama
gfr-curate 10.1093/jxb/erw425 --model ollama/llama3

# Pass an API key directly
gfr-curate 10.1093/jxb/erw425 --model gpt-4o --key <api-key>
```

### Debug Mode

Pass `--debug` to print the details of each step.

```bash
gfr-curate 10.1093/jxb/erw425 --debug
```

Debug mode can also be activated by setting the environment variable `GFR_DEBUG=1`.

### Validate Records

Validate YAML records against `schema.json`:

```bash
gfr-validate path/to/record.yml
```

Or with a custom schema file:

```bash
gfr-validate path/to/record.yml --schema path/to/schema.json
```

You can also run validation via `gfr-curate`:

```bash
gfr-curate --validate path/to/record.yml
```
