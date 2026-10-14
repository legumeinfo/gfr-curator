import json
import os
import re
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List
from rich.console import Console

err_console = Console(stderr=True)

DEFAULT_LEGUMISTA_URL = "https://mcp.legumeinfo.org"

class LegumistaMCPClient:
    """
    Client for interacting with the Legumista Model Context Protocol (MCP) server
    over Streamable HTTP / Server-Sent Events (SSE).
    """

    def __init__(self, base_url: Optional[str] = None, timeout: int = 25):
        self.base_url = (base_url or os.environ.get("LEGUMISTA_MCP_URL") or DEFAULT_LEGUMISTA_URL).rstrip("/")
        self.timeout = timeout
        self.session_id: Optional[str] = None
        self._initialized = False

    def is_healthy(self) -> bool:
        """Checks if the Legumista MCP endpoint is reachable."""
        try:
            return self._ensure_initialized()
        except Exception:
            return False

    def _ensure_initialized(self) -> bool:
        """Performs the MCP initialize handshake and captures the session ID."""
        if self._initialized and self.session_id:
            return True

        req_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "gfr-curator",
                    "version": "0.1.0"
                }
            }
        }
        
        req = urllib.request.Request(
            f"{self.base_url}/",
            data=json.dumps(req_payload).encode("utf-8"),
            headers={
                "User-Agent": "gfr-curator/0.1.0 (Mozilla/5.0)",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                session_id = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
                if not session_id:
                    # In some environments, session header might be capitalized or absent
                    pass
                self.session_id = session_id

            # Send notifications/initialized
            init_notif = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            headers = {
                "User-Agent": "gfr-curator/0.1.0 (Mozilla/5.0)",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            }
            if self.session_id:
                headers["mcp-session-id"] = self.session_id

            notif_req = urllib.request.Request(
                f"{self.base_url}/",
                data=json.dumps(init_notif).encode("utf-8"),
                headers=headers
            )
            with urllib.request.urlopen(notif_req, timeout=self.timeout):
                pass

            self._initialized = True
            return True
        except Exception as e:
            err_console.print(f"[dim yellow][!] Legumista MCP initialize failed: {e}[/dim yellow]")
            self._initialized = False
            self.session_id = None
            return False

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calls a tool on the Legumista MCP server.
        Returns the parsed result dict containing content list and isError flag.
        """
        if not self._initialized:
            if not self._ensure_initialized():
                raise ConnectionError(f"Could not connect to Legumista MCP server at {self.base_url}")

        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        headers = {
            "User-Agent": "gfr-curator/0.1.0 (Mozilla/5.0)",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id

        req = urllib.request.Request(
            f"{self.base_url}/",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_body = resp.read().decode("utf-8")
                
                # Check for SSE message format: event: message\ndata: {...}
                for line in raw_body.splitlines():
                    if line.startswith("data:"):
                        data_json = json.loads(line[5:].strip())
                        if "result" in data_json:
                            return data_json["result"]
                        elif "error" in data_json:
                            raise RuntimeError(f"MCP error from {tool_name}: {data_json['error']}")
                
                # If raw json
                try:
                    data_json = json.loads(raw_body)
                    if "result" in data_json:
                        return data_json["result"]
                    elif "error" in data_json:
                        raise RuntimeError(f"MCP error from {tool_name}: {data_json['error']}")
                except json.JSONDecodeError:
                    pass

                return {"content": [{"type": "text", "text": raw_body}], "isError": False}

        except urllib.error.HTTPError as e:
            # Re-initialize on session expiration (400 or 404 or 406 with session error)
            err_body = e.read().decode("utf-8", errors="ignore")
            if "session" in err_body.lower() or e.code in (400, 404, 406):
                self._initialized = False
                self.session_id = None
            raise RuntimeError(f"HTTP Error {e.code} calling {tool_name}: {err_body}") from e
        except Exception as e:
            raise RuntimeError(f"Error calling Legumista tool {tool_name}: {e}") from e

    # -------------------------------------------------------------------------
    # Specialized High-Level Biocuration Helpers
    # -------------------------------------------------------------------------

    def mine_gene_symbol(self, symbol: str, taxon: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Resolves a gene symbol (e.g. GmCIF1) using Legumista's mine_gene_symbol tool.
        Returns a list of parsed candidate gene records.
        """
        args: Dict[str, Any] = {"symbol": symbol}
        if taxon:
            args["taxon"] = taxon

        res = self.call_tool("mine_gene_symbol", args)
        content_items = res.get("content", [])
        if not content_items:
            return []

        text = content_items[0].get("text", "")
        records = []

        # Parse text table returned by Legumista
        # Patterns like:
        # Symbol | Symbol Long | Name | Identifier | Synopsis | DOI | in
        # or catalog: species | gene | doi | synopsis
        lines = text.splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("species |") or line.startswith("Symbol |") or line.startswith("Gene symbol"):
                continue

            parts = [p.strip() for p in line.split(" | ")]
            
            # Catalog format: species | gene | doi | synopsis
            if len(parts) == 4 and "." in parts[1]:
                gene_id = parts[1]
                # extract pub_name from gene_id (e.g. glyma.Wm82.gnm4.ann1.Glyma.17G036400 -> Glyma.17G036400)
                name_match = re.search(r"((?:Glyma|Aradu|Medtr|Phavu|Vigan|Cicar)[._\w]+)$", gene_id)
                pub_name = name_match.group(1) if name_match else gene_id.split(".")[-1]
                records.append({
                    "symbol": symbol,
                    "symbol_long": None,
                    "gene_model_pub_name": pub_name,
                    "gene_model_full_id": gene_id,
                    "synopsis": parts[3],
                    "doi": parts[2]
                })

            # Mine table format: Symbol | Symbol Long | Name | Identifier | Synopsis | DOI | in
            elif len(parts) >= 6 and (parts[0].lower() == symbol.lower() or parts[2]):
                records.append({
                    "symbol": parts[0],
                    "symbol_long": parts[1] if parts[1] else None,
                    "gene_model_pub_name": parts[2],
                    "gene_model_full_id": parts[3],
                    "synopsis": parts[4] if len(parts) > 4 and parts[4] else None,
                    "doi": parts[5] if len(parts) > 5 and parts[5] else None
                })

        return records

    def openalex_by_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves scholarly publication metadata and abstract via OpenAlex.
        """
        try:
            res = self.call_tool("openalex_by_doi", {"doi": doi})
            text = res.get("content", [{}])[0].get("text", "")
            if not text or text.startswith("error:"):
                return None

            metadata: Dict[str, Any] = {"raw": text}
            
            # Extract title: [1] <Title> (Year)
            title_match = re.search(r"\[\d+\]\s+(.+?)\s+\((\d{4})\)", text)
            if title_match:
                metadata["title"] = title_match.group(1).strip()
                metadata["year"] = title_match.group(2).strip()

            # Extract DOI & PMID
            doi_match = re.search(r"doi:([^\s|]+)", text)
            if doi_match:
                metadata["doi"] = doi_match.group(1).strip()

            pmid_match = re.search(r"pmid:(\d+)", text)
            if pmid_match:
                metadata["pmid"] = pmid_match.group(1).strip()

            # Extract authors
            authors_match = re.search(r"authors:\s*([^\n]+)", text)
            if authors_match:
                authors_str = authors_match.group(1).strip()
                # Parse authors into list of surnames
                raw_authors = [a.strip() for a in re.split(r",|\band\b", authors_str) if a.strip() and not a.startswith("(+")]
                surnames = []
                for a in raw_authors:
                    parts = a.strip().split()
                    if parts:
                        surnames.append(parts[-1])
                if surnames:
                    metadata["authors"] = surnames
                    metadata["first_author"] = surnames[0]

            # Abstract: typically follows after headers
            lines = text.splitlines()
            abstract_lines = []
            capturing_abstract = False
            for line in lines:
                if capturing_abstract:
                    abstract_lines.append(line)
                elif line.strip().startswith("authors:"):
                    capturing_abstract = True

            if abstract_lines:
                metadata["abstract"] = "\n".join(abstract_lines).strip()

            return metadata
        except Exception as e:
            err_console.print(f"[dim yellow][!] openalex_by_doi lookup failed: {e}[/dim yellow]")
            return None

    def read_paper(self, doi: str) -> Optional[str]:
        """
        Retrieves open-access full-text paper contents using Legumista's read_paper tool.
        Returns full text or None if paper is not open-access or fetch fails.
        """
        try:
            res = self.call_tool("read_paper", {"doi": doi})
            text = res.get("content", [{}])[0].get("text", "")
            if not text or not text.strip():
                return None
            clean_lower = text.lower().strip()
            if (
                clean_lower.startswith("error:")
                or "failed:" in clean_lower
                or "no open-access pdf is listed" in clean_lower
                or "no open-access" in clean_lower
                or (len(clean_lower) < 300 and ("not available" in clean_lower or "read the abstract" in clean_lower))
            ):
                return None
            return text
        except Exception as e:
            err_console.print(f"[dim yellow][!] read_paper fetch failed: {e}[/dim yellow]")
            return None

    def mine_gene_ontology(self, gene: str) -> List[Dict[str, str]]:
        """
        Retrieves curated GO annotations for a gene using Legumista's mine_gene_ontology tool.
        """
        try:
            res = self.call_tool("mine_gene_ontology", {"gene": gene})
            text = res.get("content", [{}])[0].get("text", "")
            terms = []
            for line in text.splitlines():
                # Format: Gene Name | Assembly | Term Identifier | Term Name | Ontology Name | in
                parts = [p.strip() for p in line.split(" | ")]
                if len(parts) >= 4 and parts[2].startswith("GO:"):
                    terms.append({
                        "entity": parts[2],
                        "entity_name": parts[3]
                    })
            return terms
        except Exception:
            return []

    def verify_ids(self, text: str) -> str:
        """
        Validates identifiers in text using Legumista's verify_ids tool.
        """
        try:
            res = self.call_tool("verify_ids", {"text": text})
            return res.get("content", [{}])[0].get("text", "")
        except Exception as e:
            return f"[!] Verification failed: {e}"
