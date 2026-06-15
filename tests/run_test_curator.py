from gfr_curator.curator import GFRCurator

doi = "10.1093/jxb/erw425"
api_key = "AQ.Ab8RN6LtYmczFIt8xECIQt_tQBhEejJY-FaPTARJTrTxb8ARKg"

curator = GFRCurator(doi, api_key)
curator.execute()
