import os
from dotenv import load_dotenv
from gfr_curator.curator import GFRCurator

load_dotenv()

doi = "10.1093/jxb/erw425"
api_key = os.environ.get("GEMINI_API_KEY")

curator = GFRCurator(doi, api_key)
curator.execute()
