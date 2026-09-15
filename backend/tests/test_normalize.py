from app.services.papers import normalize_title


def test_normalize_title() -> None:
    assert normalize_title("  UAV-MEC: A Study!  ") == "uav mec a study"
    assert normalize_title("灾后  多跳，计算卸载") == "灾后 多跳 计算卸载"
