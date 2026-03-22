"""Script para resetar o estado de sessão do admin"""
import requests

# Fazer login
login_resp = requests.post("http://localhost:8000/auth/login", json={
    "email": "admin@gmail.com",
    "senha": "adminpass"  # ajuste se necessário
})

if login_resp.status_code != 200:
    print(f"Login falhou: {login_resp.status_code}")
    print(login_resp.text)
    exit(1)

token = login_resp.json()["token"]
print(f"Token obtido: {token[:20]}...")

# Resetar estado via PUT /autotrade/config com amount=1
headers = {"Authorization": f"Bearer {token}"}
config_resp = requests.put("http://localhost:8000/autotrade/config", 
    headers=headers,
    json={"amount": 1.0}
)

print(f"Status: {config_resp.status_code}")
print(config_resp.json())
