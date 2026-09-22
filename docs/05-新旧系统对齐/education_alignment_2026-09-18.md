# 本次教务对齐使用的第三方组件

未复制 `旧产物/` 的源代码，也没有引入其模型配置、密钥、数据库备份或学生数据。旧源码仅用于业务语义和交互核对。

新增依赖通过包管理器使用，保留上游随包分发的许可证与版权声明；未将上游源文件直接粘贴进业务模块。

| 组件 | 本机验收版本 | 用途 | 安装包声明的许可 |
|---|---|---|---|
| Pillow | 12.3.0 | 图片校验、区域裁切、生成合成 QA 图像 | MIT-CMU |
| pypdfium2 | 5.13.0 | PDF 校验、页信息及图片渲染 | BSD-3-Clause、Apache-2.0，另有 PDFium 依赖许可 |
| Tesseract | 5.5.3 | 本地 OCR 子进程，不调用外部服务 | Apache-2.0 |
| react-markdown | 10.1.0 | 禁用 HTML/远程资源的回答渲染 | MIT |
| remark-math | 6.0.0 | Markdown 公式识别 | MIT |
| rehype-katex | 7.0.1 | KaTeX 渲染适配 | MIT |
| KaTeX | 0.16.47 | 安全公式排版，`trust=false` | MIT |

前端版本由现有 `apps/web/package-lock.json` 增量锁定。Python 依赖在 `apps/api/requirements.txt` 声明兼容区间。本轮没有重新锁定或改写其他既有依赖。

本机简体中文语言模型用于合成 OCR 验收：

- 来源：`https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/chi_sim.traineddata`
- SHA-256：`a5fcb6f0db1e1d6d8522f39db4e848f05984669172e584e8d76b6b3141e1f730`
- 仅安装到本地 Tesseract 数据目录，不加入仓库。生产 Dockerfile 使用发行版的 `tesseract-ocr-chi-sim` 与 `tesseract-ocr-eng` 包。

测试格式化工具 Prettier/Black 仅用于本轮开发，不加入产品运行依赖。
