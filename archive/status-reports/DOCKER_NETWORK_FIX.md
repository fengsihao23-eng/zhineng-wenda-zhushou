# Docker网络问题解决方案

## 问题分析
你的Docker无法连接到Docker Hub（registry-1.docker.io），这在中国大陆很常见。

## 解决方案

### 方案1: 配置Docker镜像加速器（推荐）

#### 1.1 使用阿里云镜像加速器

打开Docker Desktop → Settings → Docker Engine，添加以下配置：

```json
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com",
    "https://mirror.baidubce.com"
  ]
}
```

然后点击"Apply & Restart"。

#### 1.2 或者使用其他国内镜像源

```json
{
  "registry-mirrors": [
    "https://dockerproxy.com",
    "https://mirror.ccs.tencentyun.com",
    "https://registry.docker-cn.com"
  ]
}
```

### 方案2: 手动拉取镜像

如果配置了镜像加速器后，手动拉取：

```bash
# 拉取Python镜像
docker pull python:3.11-slim

# 拉取Node镜像（前端用）
docker pull node:18-alpine

# 查看已拉取的镜像
docker images
```

### 方案3: 使用代理

如果你有VPN或代理：

在Docker Desktop → Settings → Resources → Proxies中配置：
- HTTP Proxy: http://your-proxy:port
- HTTPS Proxy: http://your-proxy:port

### 方案4: 使用本地已有镜像或构建

修改Dockerfile使用其他基础镜像：

```dockerfile
# 使用已有的镜像或alpine
FROM alpine:3.18

# 安装Python
RUN apk add --no-cache python3 py3-pip
```

## 推荐操作步骤

```bash
# 1. 配置镜像加速器（Docker Desktop设置）

# 2. 重启Docker
# 在Docker Desktop菜单中选择 Quit Docker Desktop
# 然后重新打开Docker Desktop

# 3. 测试连接
docker pull python:3.11-slim

# 4. 如果成功，继续部署
cd /Users/hao/智能问答助手
docker compose -p intelligent-qa up -d --build
```

## 如果还是不行

使用混合部署方案（推荐）：
- Docker运行数据库（已成功）✅
- 本地运行API和前端

这样可以立即使用系统，不受网络限制。

---

需要我帮你配置镜像加速器吗？
