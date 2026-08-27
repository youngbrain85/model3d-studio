"""경로·파일명 정규화 — Windows ↔ POSIX, 한글(NFC/NFD), cp949 깨짐 방어.

이 모듈이 존재하는 이유는 전부 **실측된 실패**다 (추정이 아니다).

1. **NFD 파일명은 NFC 이름으로 열리지 않는다.** 리눅스 파일명은 불투명 바이트라
   유니코드 정규화를 하지 않는다. macOS(HFS+)가 만든 NFD 이름의 파일을 리눅스로
   가져오면 ``Path(NFC이름).exists()`` 가 **False** 다. 실측:

       (root / NFD("정밀조사_단면도.pdf")).write_bytes(b"x")
       (root / NFC("정밀조사_단면도.pdf")).exists()  -> False
       (root / NFD("정밀조사_단면도.pdf")).exists()  -> True

   → 매니페스트의 ``path`` 는 **식별자이지 열 수 있는 경로가 아니다**. 원본 파일은
   반드시 스캔이 돌려준 실제 ``Path`` 객체로만 연다. 문자열을 다시 이어붙이지 않는다.

2. **NFC 정규화는 충돌할 수 있다.** 같은 디렉터리에 NFC 이름과 NFD 이름이 **공존**하는데
   (리눅스에서 실측: 파일 2개), NFC 로 정규화하면 같은 문자열이 된다. 그대로 복사하면
   한쪽이 다른 쪽을 조용히 덮어쓴다 → 데이터 손실. 그래서 충돌을 **탐지해 거부**한다.

3. **cp949 로 깨진 파일명은 매니페스트 기록 자체를 깨뜨린다.** Windows 에서 만든 zip 을
   유니코드 미인식 unzip 으로 풀면 파일명이 유효한 UTF-8 이 아니게 되고, 파이썬은
   surrogateescape 로 ``'\\udcc1\\udca4...'`` 처럼 읽는다. ``json.dumps`` 는 통과하지만
   ``write_text(encoding="utf-8")`` 에서 터진다. 실측:

       UnicodeEncodeError: 'utf-8' codec can't encode characters ...: surrogates not allowed

   → 매니페스트를 쓰다가 알 수 없는 예외로 죽는 대신, **스캔 시점에** 무엇이 왜 문제인지
   한국어로 말하고 멈춘다.

4. **Windows 경로를 POSIX 에서 ``Path()`` 에 넣으면 조용히 한 덩어리 이름이 된다.** 실측:

       Path(r"D:\\Projects\\a").parts == ('D:\\\\Projects\\\\a',)   # 단일 요소, is_absolute()=False

   → "디렉터리가 아닙니다" 라고만 하면 사용자는 원인을 못 찾는다. Windows 경로임을
   알아채고 "지금은 Linux 다" 라고 말해 준다.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

#: 어떤 세트에서도 가져오지 않는 이름 (OS·에디터 부스러기)
DEFAULT_EXCLUDE: tuple[str, ...] = (
    "**/.DS_Store",
    "**/._*",
    "**/Thumbs.db",
    "**/desktop.ini",
    "**/~$*",  # Office 임시 파일
    "**/.git/**",
    "**/.svn/**",
    "**/*.tmp",
)


class PathPolicyError(ValueError):
    """경로·파일명이 매니페스트에 안전하게 기록될 수 없을 때."""


# ── 정규화 ────────────────────────────────────────────────────────────────
def normalize_rel_path(rel: Path | PurePosixPath | str) -> str:
    """세트 루트 기준 상대 경로를 **POSIX 구분자 + 유니코드 NFC** 로 정규화한다.

    매니페스트에 들어가는 유일한 표기이며, 이 문자열로 원본을 다시 열지 않는다.
    """
    text = str(rel).replace("\\", "/")
    return unicodedata.normalize("NFC", text)


def has_surrogates(text: str) -> bool:
    """surrogateescape 로 읽힌 비-UTF8 파일명인가 (cp949 깨짐의 신호)."""
    return any("\ud800" <= ch <= "\udfff" for ch in text)


def describe_broken_name(path: Path) -> str:
    """깨진 파일명을 사람이 고칠 수 있게 설명한다. cp949 로 되살려 후보를 보여 준다."""
    raw = os.fsencode(path.name)
    guess = ""
    for enc in ("cp949", "euc-kr", "cp932"):
        try:
            guess = raw.decode(enc)
        except UnicodeDecodeError:
            continue
        else:
            return f"{enc} 로 읽으면 '{guess}' 인 듯합니다"
    return f"원시 바이트 {raw!r}"


def assert_recordable(rel: str, path: Path) -> None:
    """매니페스트에 기록 가능한 이름인지 검사한다. 아니면 고치는 법과 함께 던진다."""
    if not has_surrogates(rel):
        return
    raise PathPolicyError(
        f"파일명이 유효한 UTF-8 이 아닙니다: {path}\n"
        f"  {describe_broken_name(path)}.\n"
        "  Windows 에서 만든 zip 을 유니코드 미인식 도구로 풀면 이렇게 됩니다.\n"
        "  해결: 원본을 다시 받거나 `unzip -O cp949` / 7-Zip 으로 다시 풀어\n"
        "  파일명이 제대로 보이는 상태로 만든 뒤 다시 ingest 하세요.\n"
        "  (매니페스트는 UTF-8 JSON 이라 이 이름을 기록할 수 없습니다.)"
    )


# ── glob (POSIX 상대 경로 대상) ───────────────────────────────────────────
def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """``**`` / ``*`` / ``?`` / ``[...]`` 를 지원하는 POSIX 스타일 glob → 정규식.

    ``*`` 는 ``/`` 를 넘지 않고 ``**`` 만 넘는다. 표준 라이브러리의 ``glob.translate`` 는
    3.13+ 전용이고 ``fnmatch`` 는 ``*`` 가 ``/`` 를 넘어가 과대매칭하므로 직접 만든다.
    정답 판별에 쓰이는 만큼 과대매칭은 실제 도면을 정답으로 오분류해 파이프라인 입력에서
    빼 버리는 사고로 이어진다.
    """
    pattern = unicodedata.normalize("NFC", pattern.replace("\\", "/"))
    out: list[str] = ["(?s:"]
    i, n = 0, len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "*":
            if pattern[i : i + 2] == "**":
                i += 2
                if pattern[i : i + 1] == "/":
                    i += 1
                    out.append("(?:[^/]+/)*")  # 0개 이상의 디렉터리
                else:
                    out.append(".*")
            else:
                i += 1
                out.append("[^/]*")
        elif ch == "?":
            i += 1
            out.append("[^/]")
        elif ch == "[":
            j = i + 1
            if j < n and pattern[j] in "!^":
                j += 1
            if j < n and pattern[j] == "]":
                j += 1
            while j < n and pattern[j] != "]":
                j += 1
            if j >= n:
                out.append(re.escape("["))
                i += 1
            else:
                body = pattern[i + 1 : j].replace("\\", "\\\\")
                if body[:1] in "!^":
                    body = "^" + body[1:]
                out.append(f"[{body}]")
                i = j + 1
        else:
            out.append(re.escape(ch))
            i += 1
    out.append(r")\Z")
    return re.compile("".join(out))


class GlobSet:
    """정규화된 상대 경로에 대해 glob 목록을 평가한다."""

    def __init__(self, patterns: tuple[str, ...] | list[str]) -> None:
        self.patterns: tuple[str, ...] = tuple(patterns)
        self._regexes = [(p, _glob_to_regex(p)) for p in self.patterns]

    def match(self, rel: str) -> str | None:
        """맞으면 **어떤 패턴에** 맞았는지 돌려준다 (근거를 남기기 위해)."""
        for pat, rx in self._regexes:
            if rx.match(rel):
                return pat
        return None

    def __bool__(self) -> bool:
        return bool(self.patterns)


# ── 스캔 ──────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class ScannedFile:
    """스캔된 파일 하나. ``path`` 만이 열 수 있는 경로이고 ``rel`` 은 식별자다."""

    path: Path
    """실제 파일 시스템 경로 — 이것으로만 연다."""
    rel: str
    """세트 루트 기준 POSIX+NFC 상대 경로 — 매니페스트 식별자."""


def _walk(root: Path) -> Iterator[Path]:
    """심볼릭 링크를 따라가지 않는 결정적 순회.

    ``Path.rglob`` 을 쓰지 않는 이유: 심볼릭 링크 디렉터리 추적 여부가 파이썬 3.12 와
    3.13 에서 다르다 (3.13 에 ``recurse_symlinks`` 가 생기며 기본이 '따라가지 않음'이 되었다).
    이 프로젝트의 하한은 3.12 이므로 버전에 따라 동작이 갈리는 API 를 쓰지 않는다.
    """
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        base = Path(dirpath)
        for name in sorted(filenames):
            p = base / name
            if p.is_symlink() or not p.is_file():
                continue
            yield p


def scan_files(root: Path, *, exclude: GlobSet | None = None) -> list[ScannedFile]:
    """세트 루트 아래 파일을 훑는다. **읽기만 한다.**

    - 제외 패턴에 걸리는 파일은 건너뛴다.
    - 기록 불가능한 파일명(cp949 깨짐)이면 즉시 던진다.
    - NFC 정규화 후 충돌하는 이름이 있으면 즉시 던진다 — 조용히 덮어쓰지 않는다.
    """
    seen: dict[str, Path] = {}
    out: list[ScannedFile] = []
    for path in _walk(root):
        rel_raw = path.relative_to(root)
        rel = normalize_rel_path(rel_raw)
        assert_recordable(rel, path)
        if exclude is not None and exclude.match(rel) is not None:
            continue
        if rel in seen:
            raise PathPolicyError(
                "유니코드 정규화(NFC) 후 두 파일의 이름이 같아집니다 — "
                "복사하면 한쪽이 다른 쪽을 덮어씁니다.\n"
                f"  {seen[rel]}\n  {path}\n"
                f"  정규화된 이름: {rel}\n"
                "  둘 중 하나의 이름을 바꾼 뒤 다시 시도하세요 "
                "(원본은 읽기 전용이므로 이 도구가 대신 바꾸지 않습니다)."
            )
        seen[rel] = path
        out.append(ScannedFile(path=path, rel=rel))
    out.sort(key=lambda f: f.rel)
    return out


# ── 낯선 플랫폼의 경로 ────────────────────────────────────────────────────
def looks_like_windows_path(raw: str) -> bool:
    """``D:\\...`` 또는 ``\\\\server\\share`` 형태인가."""
    if raw.startswith(("\\\\", "//")) and len(raw) > 2:
        return True
    return bool(PureWindowsPath(raw).drive)


def wsl_translation(raw: str) -> str | None:
    """``D:\\a\\b`` → ``/mnt/d/a/b``. WSL 사용자를 위한 **제안**이며 자동 적용하지 않는다."""
    win = PureWindowsPath(raw)
    drive = win.drive
    if len(drive) != 2 or not drive[0].isalpha() or drive[1] != ":":
        return None
    rest = "/".join(win.parts[1:])
    return f"/mnt/{drive[0].lower()}/{rest}"


def explain_unusable_source(raw: str, path: Path, env_name: str) -> str:
    """원본 경로를 쓸 수 없을 때, 왜 그런지와 무엇을 하면 되는지 한국어로 설명한다."""
    # 망가진 값은 repr 로 보여야 제어문자가 눈에 보인다. 정상 경로는 그대로 보여 준다.
    shown = repr(raw) if mangled_by_dotenv_quoting(raw) else raw
    lines = [f"원본 경로를 사용할 수 없습니다: {shown}", f"  (환경변수 {env_name})"]

    # 망가진 경로가 먼저다 — 이 경우 다른 진단은 전부 쓰레기 값을 근거로 하게 된다.
    if mangled_by_dotenv_quoting(raw):
        lines.append("  ⚠ 경로에 제어문자(줄바꿈·탭 등)가 들어 있습니다.")
        lines.append("    `.env` 에서 Windows 경로를 **큰따옴표로 감싸면** 백슬래시가 이스케이프로")
        lines.append("    해석되어 이렇게 망가집니다 (\\n→줄바꿈, \\t→탭).")
        lines.append("    따옴표를 빼거나 작은따옴표로 바꾸세요:")
        lines.append(f"      {env_name}=D:\\Projects\\...        (권장)")
        lines.append(f"      {env_name}='D:\\Projects\\...'      (가능)")
        return "\n".join(lines)

    if looks_like_windows_path(raw) and os.name != "nt":
        lines.append(f"  이것은 Windows 경로인데 지금 실행 중인 곳은 {os.uname().sysname} 입니다.")
        lines.append("  이 컨테이너/서버에는 원본이 없습니다 — 원본이 있는 머신에서 ingest 하세요.")
        wsl = wsl_translation(raw)
        if wsl:
            lines.append(f"  WSL 이라면 같은 위치가 보통 {wsl} 입니다.")
        lines.append("  매니페스트만으로 할 수 있는 일: `m3d samples verify <set_id>` (상태 보고)")
    elif not path.exists():
        lines.append(
            "  그런 경로가 없습니다. 오타이거나 외장 드라이브가 연결되지 않았을 수 있습니다."
        )
    elif not path.is_dir():
        lines.append("  파일입니다 — 세트 **디렉터리**를 가리켜야 합니다.")
    else:
        lines.append("  읽을 수 없습니다 (권한을 확인하세요).")
    return "\n".join(lines)


#: dotenv 가 큰따옴표 안 백슬래시를 이스케이프 처리해 생기는 제어문자들
_MANGLE_SIGNATURE = ("\n", "\t", "\r", "\v", "\f", "\b", "\0", "\a")


def mangled_by_dotenv_quoting(raw: str) -> bool:
    """`.env` 의 큰따옴표 때문에 경로가 망가졌는가.

    경로에 줄바꿈·탭 같은 제어문자가 들어갈 일은 사실상 없다. 있다면
    ``VAR="D:\\new\\test"`` 가 ``D:<개행>ew<탭>est`` 로 해석된 결과다 (실측 확인).
    """
    return any(ch in raw for ch in _MANGLE_SIGNATURE)


def display_path(path: Path) -> str:
    """터미널 출력용 — 깨진 이름도 예외 없이 보여 준다."""
    return os.fsdecode(path).encode("utf-8", "replace").decode("utf-8")


def posix_parts(rel: str) -> tuple[str, ...]:
    return PurePosixPath(rel).parts
