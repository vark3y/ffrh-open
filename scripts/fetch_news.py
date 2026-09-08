"""Pull the public RSS feeds and store NE development / CSR items with today's retrieval date."""
import sys; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ffrh.db import connect, init_schema
from ffrh.ingest import news
con = connect(); init_schema(con)
print(news.fetch_all(con)); con.close()
