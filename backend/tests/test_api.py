import requests
import json
import time

BASE_URL = 'http://127.0.0.1:5000'
SESSION = requests.Session()

def print_step(step_name):
    print(f"\n{'='*20} {step_name} {'='*20}")

def print_response(response):
    try:
        data = response.json()
        print(f"Status Code: {response.status_code}")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return data
    except:
        print(f"Raw Response: {response.text}")
        return None

def run_test():
    # 1. 注册用户
    print_step("1. 注册用户")
    username = f"test_user_{int(time.time())}"
    email = f"{username}@example.com"
    password = "password123"
    
    payload = {
        "username": username,
        "email": email,
        "password": password
    }
    resp = SESSION.post(f"{BASE_URL}/api/auth/register", json=payload)
    data = print_response(resp)
    
    if resp.status_code != 200:
        print("注册失败，测试停止")
        return

    # 2. 登录
    print_step("2. 用户登录")
    login_payload = {
        "username": username,
        "password": password
    }
    resp = SESSION.post(f"{BASE_URL}/api/auth/login", json=login_payload)
    data = print_response(resp)
    
    if resp.status_code != 200:
        print("登录失败，测试停止")
        return
        
    token = data['data']['access_token']
    SESSION.headers.update({'Authorization': f'Bearer {token}'})
    print(f"获取 Token 成功: {token[:20]}...")

    # 3. 获取个人信息
    print_step("3. 获取个人信息")
    resp = SESSION.get(f"{BASE_URL}/api/auth/me")
    print_response(resp)

    # 4. 创建对话
    print_step("4. 创建新对话")
    resp = SESSION.post(f"{BASE_URL}/api/conversations", json={"title": "终端测试对话"})
    data = print_response(resp)
    conversation_id = data['data']['id']

    # 5. 发送消息 (注意：如果没有配置模型API Key，这里会提示配置)
    print_step("5. 发送消息")
    msg_payload = {
        "content": "你好，这是一个测试消息。"
    }
    resp = SESSION.post(f"{BASE_URL}/api/conversations/{conversation_id}/messages", json=msg_payload)
    data = print_response(resp)

    # 检查是否提示需要配置模型
    if data and 'assistant_message' in data.get('data', {}):
        assistant_msg = data['data']['assistant_message']['content']
        print(f"\n[AI 回复]: {assistant_msg}")
    
    print_step("测试完成")

if __name__ == "__main__":
    try:
        # 检查服务是否健康
        requests.get(BASE_URL)
        run_test()
    except requests.exceptions.ConnectionError:
        print(f"错误: 无法连接到 {BASE_URL}")
        print("请确保你已经在另一个终端运行了 'python backend/main.py'")
