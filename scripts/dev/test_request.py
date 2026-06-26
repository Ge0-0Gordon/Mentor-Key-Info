import requests
import json

url = "http://127.0.0.1:9000/openai/v1/chat/completions"

payload = {
    "messages": [
        {
            "role": "user",
            "content": "你好，请介绍一下你能做什么"
        }
    ],
    "stream": False
}

resp = requests.post(url, json=payload)
print(resp.status_code)
print(json.dumps(resp.json(), ensure_ascii=False, indent=2))

content = resp.json()["choices"][0]["message"]["content"]
print("\n模型回复：")
print(content)