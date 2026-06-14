import json
from unittest.mock import MagicMock, patch

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


def test_send_posts_json_to_webhook():
    n = _make_notifier()
    card = n._build_card("标题", "green", [])
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        n._send(card)
    mock_open.assert_called_once()
    req = mock_open.call_args[0][0]
    assert req.full_url == "https://open.feishu.cn/open-apis/bot/v2/hook/fake"
    body = json.loads(req.data)
    assert body["msg_type"] == "interactive"


def test_send_silences_network_errors():
    n = _make_notifier()
    card = n._build_card("标题", "green", [])
    with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
        n._send(card)  # 不抛异常


def test_notify_start_sends_orange_card():
    n = _make_notifier()
    with patch.object(n, "_send") as mock_send:
        n.notify_start("raw", details={"因子数": "40", "workers": "16"})
    mock_send.assert_called_once()
    card = mock_send.call_args[0][0]
    assert card["card"]["header"]["template"] == "orange"
    assert "raw" in card["card"]["header"]["title"]["content"]
    fields_content = [f["text"]["content"] for f in card["card"]["elements"][0]["fields"]]
    assert any("因子数" in c for c in fields_content)


def test_notify_done_sends_green_card():
    n = _make_notifier()
    with patch.object(n, "_send") as mock_send:
        n.notify_done("preprocess", {"f_a": 100, "f_b": 200}, 23.4)
    card = mock_send.call_args[0][0]
    assert card["card"]["header"]["template"] == "green"
    fields_content = " ".join(
        f["text"]["content"] for f in card["card"]["elements"][0]["fields"]
    )
    assert "2" in fields_content   # 因子数 2
    assert "300" in fields_content  # 总行数 300
    assert "23.4" in fields_content


def test_notify_eval_done_sends_green_card():
    n = _make_notifier()
    with patch.object(n, "_send") as mock_send:
        n.notify_eval_done("evaluate", "20260614_120000", 129, 87.3)
    card = mock_send.call_args[0][0]
    assert card["card"]["header"]["template"] == "green"
    fields_content = " ".join(
        f["text"]["content"] for f in card["card"]["elements"][0]["fields"]
    )
    assert "20260614_120000" in fields_content
    assert "129" in fields_content
    assert "87.3" in fields_content


def test_notify_progress_sends_blue_card():
    n = _make_notifier()
    with patch.object(n, "_send") as mock_send:
        n.notify_progress("evaluate", 32, 129)
    card = mock_send.call_args[0][0]
    assert card["card"]["header"]["template"] == "blue"
    assert "25%" in card["card"]["header"]["title"]["content"]


def test_notify_error_sends_red_card():
    n = _make_notifier()
    with patch.object(n, "_send") as mock_send:
        n.notify_error("raw", ValueError("bad data"))
    card = mock_send.call_args[0][0]
    assert card["card"]["header"]["template"] == "red"
    fields_content = " ".join(
        f["text"]["content"] for f in card["card"]["elements"][0]["fields"]
    )
    assert "ValueError" in fields_content
    assert "bad data" in fields_content
