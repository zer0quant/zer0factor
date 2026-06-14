from zer0factor.notify.feishu import FeishuNotifier


def _make_notifier() -> FeishuNotifier:
    return FeishuNotifier("https://open.feishu.cn/open-apis/bot/v2/hook/fake")


def test_build_card_structure():
    n = _make_notifier()
    card = n._build_card(
        title="[zer0factor] `raw` 完成 ✅",
        color="green",
        fields=[("因子数", "40"), ("耗时", "5.3s")],
    )
    assert card["msg_type"] == "interactive"
    c = card["card"]
    assert c["header"]["title"]["content"] == "[zer0factor] `raw` 完成 ✅"
    assert c["header"]["template"] == "green"
    elements = c["elements"]
    assert len(elements) == 1
    assert elements[0]["tag"] == "div"
    fs = elements[0]["fields"]
    assert len(fs) == 2
    assert fs[0]["is_short"] is True
    assert "因子数" in fs[0]["text"]["content"]
    assert "40" in fs[0]["text"]["content"]


def test_build_card_no_fields():
    n = _make_notifier()
    card = n._build_card(title="标题", color="orange", fields=[])
    # 无字段时 elements 为空列表
    assert card["card"]["elements"] == []


def test_build_card_red_color():
    n = _make_notifier()
    card = n._build_card(title="出错", color="red", fields=[])
    assert card["card"]["header"]["template"] == "red"
