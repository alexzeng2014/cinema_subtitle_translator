# Cinema Subtitle Translator

AI驱动的专业电影字幕翻译系统，支持上下文感知、角色语言一致性、文化适配，远超传统翻译工具。支持多层缓存、配置管理、性能监控，适用于高质量字幕制作场景。

## 功能特色

- 🎬 智能电影知识引擎，自动分析电影风格与角色语言
- 🤖 DeepSeek API异步调用，支持高并发与重试
- 🧠 上下文感知翻译，保持情感与角色一致性
- 💾 多层缓存（内存/Redis/磁盘），高效加速翻译流程
- 🔒 安全配置管理，敏感信息加密存储
- ⚡ 性能监控与批量处理，适合大规模字幕生产

## 目录结构

```
cinema_subtitle_translator/
├── api/                # DeepSeek API客户端
├── config/             # 系统与用户配置文件
├── core/               # 翻译引擎
├── intelligence/       # 电影知识与上下文分析
├── interface/          # CLI/GUI接口（预留）
├── monitoring/         # 性能监控（预留）
├── processors/         # 处理器模块（预留）
├── resources/          # 资源文件（预留）
├── security/           # 安全与加密配置
├── storage/            # 缓存管理
├── tests/              # 单元测试
├── my-go-project/      # Go示例项目
├── requirements.txt    # Python依赖
├── pyproject.toml      # 构建配置
├── .env.example        # 环境变量示例
└── README.md           # 项目说明
```

## 安装与环境准备

1. **克隆项目**
   ```sh
   git clone <your-repo-url>
   cd cinema_subtitle_translator
   ```

2. **安装依赖**
   ```sh
   pip install -r requirements.txt
   ```

3. **环境变量配置**
   - 复制 `.env.example` 为 `.env`，并填写 DeepSeek API 密钥等敏感信息。

4. **初始化配置**
   - 首次运行时会自动生成配置文件，也可手动编辑 `config/config.yaml` 和 `config/user_preferences.yaml`。

## 快速开始

1. **运行主程序（示例）**
   ```sh
   python -m cinema_subtitle_translator
   ```

2. **翻译字幕流程**
   - 导入字幕文件（如 `.srt`）
   - 自动识别电影信息，分析角色与风格
   - 批量翻译并输出高质量字幕

3. **Go项目示例**
   - 进入 `my-go-project` 目录，运行 `go run src/main.go`

## 配置说明

- **API密钥**：通过环境变量或初始化向导设置，详见 `.env.example`
- **缓存**：支持 Redis 与磁盘缓存，参数可在 `config/config.yaml` 配置
- **用户偏好**：可自定义翻译风格、输出格式等，详见 `config/user_preferences.yaml`

## 质量保证

- 单元测试位于 `tests/` 目录
- 支持 `pytest`、`mypy`、`black` 等工具

## 贡献与反馈

欢迎提交 Issue 或 PR，完善功能与文档！

## 许可证

MIT License

---

如需详细开发文档或API接口说明，请查阅各模块源码或联系开发团