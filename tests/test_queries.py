import requests
import json

url = 'https://graphql.lis.ncgr.org/'

queries = [
    """
    {
      genes(name: "GmCIF1") {
        id
        name
      }
    }
    """,
    """
    {
      gene(name: "GmCIF1") {
        id
        name
      }
    }
    """,
    """
    {
      search(query: "GmCIF1") {
        ... on Gene {
          id
          name
        }
      }
    }
    """
]

for q in queries:
    print("Testing query...")
    response = requests.post(url, json={'query': q})
    print(json.dumps(response.json(), indent=2))
