#!/bin/bash
# 一键部署脚本 - Phase 3 智能问答助手

set -e  # 遇到错误立即退出

echo "🚀 开始部署智能问答助手 Phase 3..."
echo ""

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

echo "📂 项目目录: $PROJECT_ROOT"
echo ""

# 1. 检查Python版本
echo "1️⃣ 检查Python环境..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ 错误: 未找到python3${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo -e "${GREEN}✅ Python版本: $PYTHON_VERSION${NC}"
echo ""

# 2. 创建虚拟环境（如果不存在）
echo "2️⃣ 设置Python虚拟环境..."
cd "$PROJECT_ROOT"

if [ ! -d "venv" ]; then
    echo "创建虚拟环境..."
    python3 -m venv venv
    echo -e "${GREEN}✅ 虚拟环境已创建${NC}"
else
    echo -e "${YELLOW}⚠️  虚拟环境已存在，跳过创建${NC}"
fi
echo ""

# 激活虚拟环境
source venv/bin/activate

# 3. 升级pip
echo "3️⃣ 升级pip..."
pip install --upgrade pip -q
echo -e "${GREEN}✅ pip已升级${NC}"
echo ""

# 4. 安装后端依赖
echo "4️⃣ 安装后端依赖..."
cd "$PROJECT_ROOT/apps/api"

if pip install -r requirements.txt -q; then
    echo -e "${GREEN}✅ 后端依赖安装完成${NC}"
else
    echo -e "${RED}❌ 后端依赖安装失败${NC}"
    exit 1
fi
echo ""

# 5. 安装测试依赖
echo "5️⃣ 安装测试依赖..."
if pip install -r requirements-test.txt -q; then
    echo -e "${GREEN}✅ 测试依赖安装完成${NC}"
else
    echo -e "${YELLOW}⚠️  测试依赖安装失败，继续...${NC}"
fi
echo ""

# 6. 检查环境变量
echo "6️⃣ 检查环境配置..."
cd "$PROJECT_ROOT"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        echo "从 .env.example 创建 .env 文件..."
        cp .env.example .env
        echo -e "${YELLOW}⚠️  请编辑 .env 文件配置数据库和API密钥${NC}"
    else
        echo -e "${RED}❌ 未找到 .env.example 文件${NC}"
    fi
else
    echo -e "${GREEN}✅ .env 文件已存在${NC}"
fi
echo ""

# 7. 检查PostgreSQL
echo "7️⃣ 检查PostgreSQL..."
if command -v psql &> /dev/null; then
    echo -e "${GREEN}✅ PostgreSQL已安装${NC}"

    # 尝试连接数据库
    if psql -U postgres -c '\l' &> /dev/null; then
        echo -e "${GREEN}✅ PostgreSQL服务运行中${NC}"
    else
        echo -e "${YELLOW}⚠️  无法连接PostgreSQL，请确保服务已启动${NC}"
        echo "   启动命令: brew services start postgresql@15"
    fi
else
    echo -e "${YELLOW}⚠️  PostgreSQL未安装${NC}"
    echo "   安装命令: brew install postgresql@15"
    echo "   启动命令: brew services start postgresql@15"
fi
echo ""

# 8. 数据库迁移（如果PostgreSQL可用）
echo "8️⃣ 运行数据库迁移..."
cd "$PROJECT_ROOT/apps/api"

if command -v psql &> /dev/null && psql -U postgres -c '\l' &> /dev/null; then
    # 检查数据库是否存在
    DB_EXISTS=$(psql -U postgres -lqt | cut -d \| -f 1 | grep -w intelligent_qa | wc -l)

    if [ $DB_EXISTS -eq 0 ]; then
        echo "创建数据库 intelligent_qa..."
        psql -U postgres -c "CREATE DATABASE intelligent_qa;" 2>/dev/null || echo "数据库可能已存在"
    fi

    # 运行Alembic迁移
    if alembic upgrade head; then
        echo -e "${GREEN}✅ 数据库迁移完成${NC}"
    else
        echo -e "${YELLOW}⚠️  数据库迁移失败，请检查配置${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  跳过数据库迁移（PostgreSQL未配置）${NC}"
fi
echo ""

# 9. 初始化Prompt模板
echo "9️⃣ 初始化Prompt模板..."
cd "$PROJECT_ROOT/apps/api"

if python -c "from app.core.database import get_db; print('DB OK')" 2>/dev/null | grep -q "DB OK"; then
    if python -m scripts.init_prompts; then
        echo -e "${GREEN}✅ Prompt模板初始化完成${NC}"
    else
        echo -e "${YELLOW}⚠️  Prompt初始化失败${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  跳过Prompt初始化（数据库未连接）${NC}"
fi
echo ""

# 10. 运行测试
echo "🔟 运行测试验证..."
cd "$PROJECT_ROOT/apps/api"

if pytest -q 2>/dev/null; then
    echo -e "${GREEN}✅ 测试通过${NC}"
else
    echo -e "${YELLOW}⚠️  部分测试失败或未运行${NC}"
fi
echo ""

# 11. 检查前端环境
echo "1️⃣1️⃣ 检查前端环境..."
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo -e "${GREEN}✅ Node.js版本: $NODE_VERSION${NC}"

    cd "$PROJECT_ROOT/apps/web"
    if [ ! -d "node_modules" ]; then
        echo "安装前端依赖..."
        if npm install; then
            echo -e "${GREEN}✅ 前端依赖安装完成${NC}"
        else
            echo -e "${YELLOW}⚠️  前端依赖安装失败${NC}"
        fi
    else
        echo -e "${GREEN}✅ 前端依赖已安装${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Node.js未安装${NC}"
    echo "   安装命令: brew install node"
fi
echo ""

# 12. 总结
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✅ 部署完成！${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 下一步操作："
echo ""
echo "1. 配置环境变量:"
echo "   vi .env"
echo ""
echo "2. 启动后端服务:"
echo "   cd apps/api"
echo "   source ../../venv/bin/activate"
echo "   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "3. 启动前端服务 (新终端):"
echo "   cd apps/web"
echo "   npm run dev"
echo ""
echo "4. 访问应用:"
echo "   前端: http://localhost:3000"
echo "   API文档: http://localhost:8000/docs"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📖 查看文档:"
echo "   - docs/PHASE3_QUICKSTART.md"
echo "   - docs/PHASE3_DEPLOYMENT.md"
echo ""
