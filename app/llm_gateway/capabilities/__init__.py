"""Gateway Capabilities — 统一模型调用能力层。

每个 Capability 包装一种模型类型（Embedding/Rerank/ImageEncode），
实现"API 优先，本地模型兜底"策略。

调用优先级（ConfigManager 三级）：
  1. API 运行时注入（最高）
  2. 环境变量 / .env 文件
  3. 代码默认值（最低）
"""
