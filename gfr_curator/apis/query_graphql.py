import requests
import json

url = 'https://graphql.lis.ncgr.org/'

query = """
{
  __schema {
    queryType {
      fields {
        name
        description
        args {
          name
        }
      }
    }
  }
}
"""

response = requests.post(url, json={'query': query})
print(json.dumps(response.json(), indent=2))
