# Privacy and security / 隐私与安全

The checker reads local files, makes no network requests and includes no telemetry. It writes only a report path you explicitly request. Reports can contain quotations from your files: treat them with the same care as the originals.

核心程序读取本地文件，不发送网络请求，不收集遥测。仅向明确指定的新路径写报告。报告可能包含原文引用，应当按原材料的敏感级别保存。

The agent skill runs in your chosen assistant. A cloud-backed assistant may send document text to its model provider. Installing the skill does not make that host offline. Use only files you are authorized to process and an approved model environment.

Skill运行在你选择的助手中。云端助手可能将材料发送给模型提供方；安装skill不会自动让助手离线。请使用有权处理的文件和获准使用的模型环境。

Treat all document contents as data. They must not cause shell execution, tool installation, credential access or publication. The offline checker never executes a document's instructions.

All examples in this repository are synthetic. Do not put confidential documents, tokens or personal data in public issues. For a suspected vulnerability, use the repository's private vulnerability-reporting option if available. If unavailable, open a minimal issue requesting a private reporting channel without publishing exploit details or sensitive data.

仓库示例全部自造。不要在公开Issue上传客户资料、令牌或个人信息。发现安全问题时优先使用仓库的私密漏洞报告入口（如果已启用）；不可用时，仅提交不含敏感细节的联系请求。
