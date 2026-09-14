#!/usr/bin/env python3
"""
简单的API测试脚本
"""
import requests
import json
import sys

API_BASE = "http://localhost:8000"

def test_health():
    """测试健康检查"""
    print("1. 测试健康检查...")
    response = requests.get(f"{API_BASE}/api/health")
    print(f"   状态码: {response.status_code}")
    print(f"   响应: {response.json()}")
    assert response.status_code == 200
    print("   ✅ 健康检查通过\n")

def test_login():
    """测试登录"""
    print("2. 测试用户登录...")
    response = requests.post(
        f"{API_BASE}/api/v1/auth/login",
        json={
            "username": "test_student",
            "password": "password123"
        }
    )
    print(f"   状态码: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ 登录成功")
        print(f"   Access Token: {data['access_token'][:50]}...")
        return data['access_token']
    else:
        print(f"   ❌ 登录失败: {response.text}")
        return None

def test_get_user_info(token):
    """测试获取用户信息"""
    print("3. 测试获取用户信息...")
    response = requests.get(
        f"{API_BASE}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"   状态码: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"   ✅ 获取成功")
        print(f"   用户名: {data['username']}")
        print(f"   显示名: {data.get('display_name', 'N/A')}")
        print(f"   学校ID: {data['school_id']}")
        print(f"   学生ID: {data.get('student_id', 'N/A')}")
        print(f"   角色: {', '.join(data['roles'])}")
    else:
        print(f"   ❌ 获取失败: {response.text}")
    print()

def main():
    """主函数"""
    print("="*60)
    print("智能问答助手 - API测试脚本")
    print("="*60)
    print()

    try:
        # 1. 健康检查
        test_health()

        # 2. 登录
        token = test_login()
        if not token:
            print("❌ 测试失败：无法登录")
            sys.exit(1)
        print()

        # 3. 获取用户信息
        test_get_user_info(token)

        print("="*60)
        print("✅ 所有测试通过！")
        print("="*60)
        print()
        print("你可以使用以下Token测试其他API：")
        print(f"Authorization: Bearer {token}")
        print()

    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到API服务器")
        print("请确保服务正在运行：")
        print("  docker-compose up -d api")
        print("  或")
        print("  cd apps/api && uvicorn app.main:app --reload")
        sys.exit(1)
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
