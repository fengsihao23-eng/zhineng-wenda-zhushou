#!/usr/bin/env python3
"""
简单的Chat API客户端示例
演示如何使用流式和非流式对话接口
"""
import asyncio
import httpx
import json
from typing import Optional


class ChatClient:
    """聊天客户端"""

    def __init__(self, base_url: str = "http://localhost:8000", token: Optional[str] = None):
        self.base_url = base_url
        self.token = token
        self.session_id = None

    def _get_headers(self):
        """获取请求头"""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def chat(self, message: str, stream: bool = False) -> dict:
        """
        发送聊天消息（非流式）
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/chat",
                json={
                    "message": message,
                    "session_id": self.session_id,
                    "stream": stream
                },
                headers=self._get_headers()
            )
            response.raise_for_status()
            result = response.json()

            # 保存session_id以便后续使用
            if not self.session_id:
                self.session_id = result.get("session_id")

            return result

    async def chat_stream(self, message: str):
        """
        发送聊天消息（流式）
        """
        async with httpx.AsyncClient(timeout=60.0) as client:
            request_data = {
                "message": message,
                "session_id": self.session_id,
                "stream": True
            }

            async with client.stream(
                "POST",
                f"{self.base_url}/api/v1/chat/stream",
                json=request_data,
                headers=self._get_headers()
            ) as response:
                response.raise_for_status()

                # 解析SSE事件流
                full_answer = ""
                async for line in response.aiter_lines():
                    if line.startswith("event:"):
                        event_type = line.split(":", 1)[1].strip()
                    elif line.startswith("data:"):
                        data_str = line.split(":", 1)[1].strip()
                        try:
                            data = json.loads(data_str)

                            if event_type == "context_loaded":
                                print(f"📚 学生: {data.get('student_name')}")
                                print(f"🎓 权益: {data.get('entitlement_level')}")

                            elif event_type == "intent_detected":
                                print(f"🎯 意图: {data.get('name')} (置信度: {data.get('confidence')})")

                            elif event_type == "tool_call_start":
                                print(f"🔧 调用工具: {data.get('tool_name')}")

                            elif event_type == "tool_call_complete":
                                print(f"✅ 工具完成: {data.get('tool_name')}")

                            elif event_type == "answer_chunk":
                                chunk = data.get("chunk", "")
                                print(chunk, end="", flush=True)
                                full_answer += chunk

                            elif event_type == "answer_complete":
                                print("\n")
                                print(f"📊 工具调用次数: {data.get('total_tools_called')}")

                            elif event_type == "done":
                                session_id = data.get("session_id")
                                if not self.session_id:
                                    self.session_id = session_id

                            elif event_type == "error":
                                print(f"❌ 错误: {data.get('error')}")

                        except json.JSONDecodeError:
                            pass

                return full_answer

    async def get_sessions(self):
        """获取会话列表"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/sessions",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()

    async def get_messages(self, session_id: str):
        """获取会话消息历史"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/api/v1/sessions/{session_id}/messages",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()


async def demo_non_stream():
    """演示非流式对话"""
    print("=" * 60)
    print("非流式对话示例")
    print("=" * 60)

    client = ChatClient()

    # 注意：这里需要真实的JWT token
    # client.token = "YOUR_JWT_TOKEN_HERE"

    questions = [
        "这次考试考得怎么样？",
        "数学考了多少分？",
        "比上次进步了吗？",
    ]

    for question in questions:
        print(f"\n❓ 问题: {question}")
        try:
            result = await client.chat(question)
            print(f"✅ 回答: {result['answer']}")
            print(f"📊 工具调用: {result['tools_called']} 次")
        except httpx.HTTPStatusError as e:
            print(f"❌ 请求失败: {e.response.status_code}")
            print(f"   详情: {e.response.text}")
        except Exception as e:
            print(f"❌ 错误: {e}")


async def demo_stream():
    """演示流式对话"""
    print("\n" + "=" * 60)
    print("流式对话示例")
    print("=" * 60)

    client = ChatClient()

    # 注意：这里需要真实的JWT token
    # client.token = "YOUR_JWT_TOKEN_HERE"

    questions = [
        "这次考试考得怎么样？",
        "哪些题目丢分最多？",
    ]

    for question in questions:
        print(f"\n❓ 问题: {question}")
        print("-" * 60)
        try:
            await client.chat_stream(question)
        except httpx.HTTPStatusError as e:
            print(f"❌ 请求失败: {e.response.status_code}")
            print(f"   详情: {e.response.text}")
        except Exception as e:
            print(f"❌ 错误: {e}")


async def demo_authentication():
    """演示如何获取JWT token"""
    print("\n" + "=" * 60)
    print("认证示例")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
        # 1. 登录获取token
        print("\n1️⃣ 登录获取JWT token...")
        try:
            response = await client.post(
                "http://localhost:8000/api/v1/auth/login",
                json={
                    "username": "student1",  # 替换为真实用户名
                    "password": "password123"  # 替换为真实密码
                }
            )
            response.raise_for_status()
            auth_data = response.json()
            token = auth_data["access_token"]
            print(f"✅ Token获取成功: {token[:20]}...")

            # 2. 使用token进行对话
            print("\n2️⃣ 使用token进行对话...")
            chat_client = ChatClient(token=token)
            result = await chat_client.chat("这次考试考得怎么样？")
            print(f"✅ 回答: {result['answer'][:100]}...")

        except httpx.HTTPStatusError as e:
            print(f"❌ 认证失败: {e.response.status_code}")
            print(f"   详情: {e.response.text}")
        except Exception as e:
            print(f"❌ 错误: {e}")


async def interactive_mode():
    """交互式对话模式"""
    print("\n" + "=" * 60)
    print("交互式对话模式")
    print("=" * 60)
    print("输入 'quit' 退出，输入 'sessions' 查看会话列表")
    print("-" * 60)

    client = ChatClient()

    # 获取token（实际使用时需要先登录）
    token = input("请输入JWT token（可选，直接回车跳过）: ").strip()
    if token:
        client.token = token

    while True:
        try:
            user_input = input("\n您: ").strip()

            if not user_input:
                continue

            if user_input.lower() == 'quit':
                print("再见！")
                break

            if user_input.lower() == 'sessions':
                sessions = await client.get_sessions()
                print(f"\n📋 会话列表 ({len(sessions.get('sessions', []))} 个):")
                for session in sessions.get('sessions', []):
                    print(f"  - {session['title'][:50]} ({session['created_at']})")
                continue

            # 流式对话
            print("\nAI: ", end="", flush=True)
            await client.chat_stream(user_input)

        except KeyboardInterrupt:
            print("\n\n再见！")
            break
        except Exception as e:
            print(f"\n❌ 错误: {e}")


async def main():
    """主函数"""
    print("\n🤖 Chat API 客户端示例")
    print("=" * 60)
    print("\n请选择演示模式:")
    print("1. 非流式对话")
    print("2. 流式对话")
    print("3. 认证示例")
    print("4. 交互式模式")
    print("0. 退出")

    choice = input("\n请选择 (0-4): ").strip()

    if choice == "1":
        await demo_non_stream()
    elif choice == "2":
        await demo_stream()
    elif choice == "3":
        await demo_authentication()
    elif choice == "4":
        await interactive_mode()
    elif choice == "0":
        print("再见！")
    else:
        print("无效选择")


if __name__ == "__main__":
    asyncio.run(main())
