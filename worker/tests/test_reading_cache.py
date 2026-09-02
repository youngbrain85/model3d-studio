"""판독 캐시 — 재실행을 무과금으로 만드는 장치. 키가 헐거우면 낡은 결과를 쓴다."""

from pydantic import BaseModel

from m3d.reading.cache import cache_key, load_cached, save_cached, schema_fingerprint


class Out1(BaseModel):
    a: str


class Out2(BaseModel):
    a: str
    b: int = 0


def _payload(**kw):
    base = {"kind": "sheet", "model": "claude-sonnet-5", "max_tokens": 8000,
            "system": "당신은 판독자다.", "schema": "deadbeef",
            "user_text": ["시트를 판독하라"], "inputs": {"ord": "B01", "text_sha": "abc"}}
    base.update(kw)
    return base


def test_key_is_stable_across_dict_order():
    a = cache_key({"model": "s", "system": "x", "sheet": "abc"})
    b = cache_key({"sheet": "abc", "system": "x", "model": "s"})
    assert a == b


def test_key_changes_with_any_field():
    k0 = cache_key(_payload())
    assert cache_key(_payload(model="claude-fable-5")) != k0     # 모델 변경
    assert cache_key(_payload(max_tokens=4000)) != k0            # 토큰 상한 변경
    assert cache_key(_payload(schema="cafe")) != k0              # 출력 스키마 변경
    assert cache_key(_payload(user_text=["다르게 판독하라"])) != k0  # user 지시문 변경
    assert cache_key(_payload(inputs={"ord": "B02", "text_sha": "abc"})) != k0  # 입력 변경


def test_key_changes_with_one_char_in_system():
    """프롬프트를 한 글자만 고쳐도 그 호출은 캐시 미스가 된다 — 버전 상수가 필요 없는 이유."""
    k0 = cache_key(_payload())
    assert cache_key(_payload(system="당신은 판독자다!")) != k0


def test_schema_fingerprint_changes_when_field_added():
    """출력 스키마가 바뀌면 낡은 캐시를 조용히 재사용하지 않는다."""
    assert schema_fingerprint(Out1) == schema_fingerprint(Out1)
    assert schema_fingerprint(Out1) != schema_fingerprint(Out2)


def test_key_is_hex_sha256():
    k = cache_key({"a": 1})
    assert len(k) == 64 and all(c in "0123456789abcdef" for c in k)


def test_save_load_roundtrip_utf8(tmp_path):
    p = tmp_path / "x.json"
    data = {"readings": [{"item": "슬래브 두께", "value_raw": "300"}]}
    save_cached(p, data)
    assert load_cached(p) == data
    assert "슬래브" in p.read_text(encoding="utf-8")   # ensure_ascii=False


def test_load_missing_returns_none(tmp_path):
    assert load_cached(tmp_path / "none.json") is None


def test_load_corrupt_returns_none(tmp_path):
    """손상 캐시는 무시하고 재호출한다 — 죽지 않는다."""
    p = tmp_path / "bad.json"
    p.write_text("{ not json", encoding="utf-8")
    assert load_cached(p) is None
