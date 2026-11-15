# Contributing / 参与贡献

We welcome small, reproducible reports of false alarms and missed discrepancies, bilingual documentation improvements, and focused fixes. Please start with an issue for new behavior so its business meaning and scope can be discussed.

欢迎提交误报、漏检、双语说明改进与小范围修复。新增能力请先说明具体业务输入、期望结果和使用边界。

## Reproduce safely

1. Replace customer information with fictional names and values. Never upload a real contract or confidential report.
2. Include the tool version, Python version, command, minimum source/draft or manifest, expected behavior and actual behavior.
3. Explain why the two claims refer to the same business scope. A matching number alone is not enough.

请提供自造的最小样例、版本、运行命令、预期和实际结果；同时说明两项事实为何应当比较。

## Local development

```bash
python -m venv .venv
# Activate the environment, then:
python -m pip install -e .
python -m unittest discover -s tests -v
```

Add a failing behavioral test before a bug fix, then run the full suite. Include a valid equivalent case as well as a discrepancy where useful. Do not add network calls, telemetry or external model dependencies to the offline core.

修改误报或漏检时，先用测试复现，再修复并运行全套测试。能体现同类误报风险时，也请加入一个实际等价的正例。核心程序保持离线，不加入遥测或外部模型依赖。

Changes to supported behavior should update both README languages and CHANGELOG.md. Use project-specific facts only with permission; submit original work or clearly attributed compatible-licensed contributions.
