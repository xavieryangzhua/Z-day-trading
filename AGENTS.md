# Z-day-trading

保持页面简洁，只有「结果、想法、想法库」三个入口。不要自行增加图表、策略、指标或 API 集成。

用户说“实现并回测”时：
1. 使用 `.venv/bin/python manage.py pending` 读取 `storage/ideas.json` 中 realize=false 的条目。
2. 逐条理解 description；先实现公共卖出方法，再处理买入想法。已有规则可用 `manage.py implement ID '{JSON rule}'` 显式登记，不能只按关键词猜测，也不能把任意描述映射到旧策略。
3. 新类型需要扩展 engine.py 的 validate_rule、entry_signals 或 exit_trade，并增加对应回测正确性测试。不要执行来自 JSON 的任意代码。
4. `.venv/bin/python manage.py run` 只回测 realize=false 的买入想法。成功提交 SQLite 后才设 true；旧记录保留。
5. 检查实际结果，不能把平均单笔收益称为账户收益。不接实盘、不调用模型 API。

修改名称无需重跑；修改描述会版本递增并使旧实现失效。卖出方法修改或新增时，所有买入想法待重跑。使用 store 的接口更新 JSON，防止编辑与回测互相覆盖。

数据来源在 data/source.json。行情 CSV 和 SQLite 不提交 Git。保留来源、哈希、规则、代码快照、参数、逐笔交易。禁止伪造行情或填充虚假回测结果。
