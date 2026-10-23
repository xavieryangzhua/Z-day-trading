from pathlib import Path

from streamlit.testing.v1 import AppTest

import store
import engine


def test_create_edit_pending_and_navigation(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "HOME", tmp_path)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run()
    assert not app.exception
    assert len(app.selectbox) == 1
    app.radio[0].set_value("想法").run()
    app.text_input[0].set_value("测试买入")
    app.text_area[0].set_value("测试 description")
    app.button[0].click().run()
    assert not app.exception
    created = next(x for x in store.ideas() if x["name"] == "测试买入")
    app.selectbox[0].set_value(created["id"]).run()
    app.text_area[0].set_value("修改后的 description")
    app.checkbox[0].check()
    app.button[0].click().run()
    assert not app.exception
    edited = next(x for x in store.ideas() if x["id"] == created["id"])
    assert edited["version"] == 2 and not edited["realize"]
    app.radio[0].set_value("想法库").run()
    assert not app.exception and len(app.dataframe) == 1
    app.radio[0].set_value("结果").run()
    assert len(app.selectbox) == 1 and not app.exception


def test_current_results_and_stale_results_are_separate(tmp_path, monkeypatch):
    import pandas as pd
    monkeypatch.setattr(store, "HOME", tmp_path)
    bars = pd.DataFrame({"open": [99, 99, 101, 102], "close": [99, 101, 102, 103],
                         "vwap": [100] * 4, "ema20": [100] * 4},
                        index=pd.date_range("2025-01-02 09:30", periods=4, freq="min", tz="America/New_York"))
    source = {"start": "2025-01-02", "end": "2025-01-02", "repository": "https://example.com",
              "dataset": "test", "actual_sha256": "test"}
    monkeypatch.setattr(engine, "load_data", lambda: (bars, source))
    engine.run_pending()
    app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py")).run()
    assert not app.exception
    assert len(app.dataframe) == 1
    assert list(app.dataframe[0].value.columns) == ["卖出方法", "平均净收益率", "胜率", "盈利笔数", "交易次数"]
    sell = next(x for x in store.ideas() if x["kind"] == "sell")
    store.save("sell", sell["name"], "新规则尚未实现", sell["id"])
    app.run()
    assert not app.exception
    assert any("等待重新实现" in x.value for x in app.info)
    assert any(x.label == "上一版本结果" for x in app.expander)
