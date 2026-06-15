# LIS Gene Function Registry (GFR) Curation Assistant (`gfr-curator`)

An automated, curator CLI tool for the Legume Information System [Gene Function Registry](https://github.com/legumeinfo/gene-function-registry). Given a research paper DOI, the tool retrieves metadata and abstracts, then uses Gemini to extract gene functions, resolves ontology terms in real-time, and produces a valid GFR-compliant YAML record draft.

## Installation

To install the tool in editable mode:

```bash
cd gfr-curator
pip install -e .
```
Or with venv:

```bash
cd gfr-curator
python -m venv venv
source venv/bin/activate
pip install -e .
```

## Usage

Ensure your Gemini API Key is set first:
```bash
export GEMINI_API_KEY="your_api_key_here"
```
Or, create a `.env` file in the `gfr-curator` directory with the following content:
```dotenv
GEMINI_API_KEY="your_api_key_here"
```

### 1. Interactive Mode
Run the tool without arguments:
```bash
gfr-curate
```

### 2. Direct Mode
Provide the DOI as a command-line argument:
```bash
gfr-curate 10.1093/jxb/erw425
```
Or pass the key directly as an argument:
```bash
gfr-curate 10.1093/jxb/erw425 --key your_api_key_here
```

### Output

The generated GFR-compliant YAML drafts will be saved automatically to your current working directory.
