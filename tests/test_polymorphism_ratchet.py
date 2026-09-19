# tests/test_polymorphism_ratchet.py
"""다형성 래칫 — 종류 분기가 **늘지 않는지** 소스 AST로 감시한다 (WP-0 안전망).

사용자 지시(2026-09-19): *"isinstance 호출이 과도하게 많다면 다형성을 사용하고
있지 않은 것이다."* 리팩토링은 이 수를 단계적으로 내린다. 이 테스트는 그 수가
**올라가지 않는 것**만 보장한다 — 내리는 것은 각 WP의 일이고, 올리는 커밋은
리뷰가 거부한다.

세 래칫(REFACTOR_SPEC §8 ①② + WP-11 ③):

① **컴포넌트 클래스 대상 `isinstance`** — 두 번째 인자(튜플/리스트/집합 포함)에
   컴포넌트·config 클래스 이름이 든 호출. "이 객체가 무슨 종류인가"를 타입으로
   묻는 자리이며, 대부분은 종류가 아니라 **성질**을 묻고 있다.

② **컴포넌트 형상 `getattr`/`hasattr`** — 두 번째 인자가 컴포넌트 형상 속성
   이름 상수인 호출. 타입 대신 문자열로 같은 질문을 하는 우회로다.
   첫 인자가 `project`/`cfg`/`config`/`doc`인 호출은 **제외**한다 — 그쪽은
   컴포넌트 형상이 아니라 프로젝트/설정 dict의 하위 호환 조회다.

③ **FSM 상태·전략·훅 핸들러·Tool 클래스 대상 `isinstance`** — 컴포넌트 종류가
   아니지만 같은 결함 형태(병렬 사다리)라 같은 규칙으로 감시한다. WP-11이
   서술 사다리·폼 사다리·의사 상태 사다리·Tool 사다리를 걷어 89 → 53이 됐다.
   남은 53의 대부분은 검증 규칙(`machine_rules`)과 FSM 직렬화의 구조 순회로,
   "종류를 묻는" 것이 아니라 "구조를 내려가는" 자리다.

세 래칫 모두 **기준선은 이 저장소에서 실측했다**(명세의 숫자를 베끼지 않았다).
면제는 `module::qualname`으로 적는다 — 줄 번호로 적으면 위아래 편집만으로
면제가 엉뚱한 자리로 미끄러진다.
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "daedalus"

# ── 컴포넌트/설정 클래스 이름 29종 (구체 9 + 추상 5 + 믹스인 1 + config 14) ──
# WP-9가 `ExternalAgent`/`ExternalAgentConfig`를, WP-10이 `WrappedSkill`/
# `WrappedSkillConfig`를 갈아 끼웠다 — 없는 클래스 이름을 남겨 두면 스캐너가
# 아무것도 세지 않는 표적을 들고 다니게 된다.
COMPONENT_CLASS_NAMES: frozenset[str] = frozenset({
    # 추상 기저 + 믹스인
    "PluginComponent", "Skill", "StepSkill", "ForkSkill", "Agent", "WorkflowComponent",
    # 구체 컴포넌트 9종
    "ProceduralSkill", "SyncForkSkill", "AsyncForkSkill", "DeclarativeSkill",
    "TransferSkill", "ReferenceSkill", "AgentDefinition", "ForkAgent",
    "ExternalAgent",
    # config 14종
    "ComponentConfig", "SkillConfig", "StepSkillConfig", "ProceduralSkillConfig",
    "ForkSkillConfig", "SyncForkSkillConfig", "AsyncForkSkillConfig",
    "DeclarativeSkillConfig", "AgentConfigBase", "AgentConfig",
    "ForkAgentConfig", "TransferSkillConfig", "ReferenceSkillConfig",
    "ExternalAgentConfig",
})

# ── 컴포넌트 형상 속성 (§8 래칫 ② 목록 + output_events/output_event_defs) ──
# `output_events`/`output_event_defs`는 WP-2d에서 모델에서 **삭제**됐다(소비자
# 0). 목록에는 남겨 둔다 — 같은 우회로가 다시 생기면 즉시 걸려야 한다.
SHAPE_ATTRS: frozenset[str] = frozenset({
    "config", "body", "fsm", "transfer_on", "call_agents", "when_to_use",
    "usage", "enabled", "reference_placements", "source",
    "output_events", "output_event_defs",
})

# ── FSM·전략·훅 핸들러·Tool 클래스 35종 (§5 말미 ①~⑤의 사정권) ──
FSM_CLASS_NAMES: frozenset[str] = frozenset({
    # FSM 상태(+ Region) 9종
    "State", "SimpleState", "CompositeState", "ParallelState", "Region",
    "ChoiceState", "TerminateState", "EntryPoint", "ExitPoint",
    # 평가/실행 전략 11종
    "EvaluationStrategy", "LLMEvaluation", "ToolEvaluation", "MCPEvaluation",
    "ExpressionEvaluation", "CompositeEvaluation",
    "ExecutionStrategy", "LLMExecution", "ToolExecution", "MCPExecution",
    "CompositeExecution",
    # 이벤트 5종
    "Event", "StateEvent", "CompletionEvent", "BlackboardEvent", "BlackboardTrigger",
    # 훅 핸들러 6종
    "HookHandler", "CommandHook", "PromptHook", "AgentHook", "HttpHook", "McpToolHook",
    # Tool 4종
    "Tool", "BuiltinTool", "MCPTool", "UserDefinedTool",
})

#: 첫 인자가 이것들이면 컴포넌트 형상 질문이 아니다(프로젝트/설정/문서 조회).
SHAPE_EXCLUDED_SUBJECTS: frozenset[str] = frozenset({"project", "cfg", "config", "doc"})

#: 실측 기준선 (2026-09-19, WP-4 완료 — 직렬화 선언화). **내리기만 한다.**
#: compiler 패키지의 컴포넌트 대상 isinstance·형상 getattr는 **둘 다 0**이고,
#: WP-4가 `serialize/ser.py`도 0으로 비웠다(11 → 0 — `_ser_config` 사다리 8 +
#: `_ser_skill`/`_ser_agent` 형상 가드 3이 `SERIALIZED_FIELDS` 선언과
#: `component_fields`의 키 순서 표로 대체됐다).
#: WP-6이 미리보기 분기 3(`view/actions/preview`의 2 + `mcp/tools/query`의 1)을
#: 없앴다 — 종류별 컴파일러 선택이 `compiler/preview.preview_component` 하나가
#: 되면서 표면마다 `isinstance(comp, Agent)`를 묻던 자리가 사라졌다(23 → 20).
#: WP-7이 뷰의 kind 표 여섯 벌을 `view/kind_ui.KIND_UI` 한 표로 모으면서
#: 레지스트리 패널 10·탭 열기 2·탭 접두 2·캔버스 드롭 1·위젯 표 선택 1을
#: 걷었다(20 → 4). 남은 4는 레지스트리 조회 1(`kinds::spec_for` — 예정 면제)과
#: 랩핑 전용 분기 3(`wrapped_usage` — WP-10이 클래스와 함께 지운다)이다.
#: 마무리 커밋(2026-09-19)이 `model_effort`의 방어적 `config` 조회 3벌을
#: `_config_of` 하나로 모으고 그 한 자리를 면제로 등재했다(21/10 → 18/9) —
#: REFACTOR_SPEC §8 래칫 ②의 최종 목표 ≤20을 넘겼다. 남은 18 중
#: `hook_panel`·`_base`의 `enabled` 3건은 `HookDef` 속성이라 스캐너 오탐이고,
#: 진짜 잔여는 `frontmatter_panel` 6 · `component_editor` 3이다(backlog §7).
#: 형상 getattr 래칷(②)은 WP-4가 건드리지 않았다 — 직렬화 경로의 남은 두 사이트
#: (`deser.deserialize_project`의 `fsm`)는 프로젝트 그래프 2-pass 질문이지
#: 컴포넌트 조립 질문이 아니라 여기서 죽지 않는다.
#: WP-8이 MCP의 종류·필드 허용을 레지스트리·`SKILL_FIELD_MATRIX`에서 파생시키며
#: `mcp/tools/props`의 형상 getattr을 걷었다(33 → 25). WP-7·WP-8을 합치면 형상
#: 래칫은 23/10파일이고, 병합 후 **재실측한 값**을 잠갔다 — 두 가지의 감소분을
#: 더하면 겹치는 자리를 두 번 세게 된다.
#: WP-11이 래칫 ③을 도입하며 병렬 사다리 넷을 걷었다(89/17 → 53/12):
#: 상태 서술 13 + legacy 에이전트 변형 5 + 훅 핸들러 폼 10 + 의사 상태 5 +
#: Tool 직렬화 3. 남은 자리는 **종류 질문이 아니라 구조 순회**다 — 합성 상태를
#: 재귀로 내려가거나(`walk`·`machine_rules`), FSM 값 객체를 저장 dict로
#: 펴는(`ser`) 자리이고, 폴리모픽 메서드로 바꾸려면 fsm 레이어에 컴파일러·
#: 검증 어휘를 들이게 된다(경계 계약 위반). 더 내리려면 별도 WP가 소유한다.
RATCHET: dict[str, int] = {
    "isinstance_sites": 1,
    "isinstance_files": 1,
    "shape_attr_sites": 18,
    "shape_attr_files": 9,
    "fsm_isinstance_sites": 52,
    "fsm_isinstance_files": 11,
}

#: 정당한 잔존 사이트 — `module::qualname`. 면제는 **사유와 철거 주체**를 적는다.
#: 리팩토링 종료 시점의 예정 면제는 `kinds::spec_for`와
#: `deser_plugin::_coerce_config`(역직렬화 안전망) 둘이다.
ISINSTANCE_EXEMPT: dict[str, str] = {}
SHAPE_ATTR_EXEMPT: dict[str, str] = {
    # 캔버스 우클릭의 입구라 인수에 컴포넌트가 아닌 것이 섞인다(빈 노드의
    # `skill_ref=None`·의사 상태). 컴포넌트 **형상**을 묻는 자리가 아니라
    # **컴포넌트인지부터 모르는** 자리라 방어적 조회가 맞다. 세 함수가 손으로
    # 베끼던 같은 조회를 이 한 곳으로 모았다(원칙 1) — 철거 주체는 캔버스가
    # skill_ref를 컴포넌트로 좁히는 WP다.
    "view.actions.model_effort::_config_of":
        "의사 상태·빈 노드까지 오는 자리의 방어적 조회 — 컴포넌트 형상 질문이 아니다",
}
FSM_ISINSTANCE_EXEMPT: dict[str, str] = {}


# ─────────────────────────── AST 스캐너 ───────────────────────────

def _module_name(path: Path) -> str:
    return path.relative_to(_SRC).with_suffix("").as_posix().replace("/", ".")


def _qualname_map(tree: ast.AST) -> dict[int, str]:
    """노드 id → 소속 qualname. 면제 키를 줄 번호가 아니라 이름으로 쓰기 위함."""
    out: dict[int, str] = {}

    def walk(node: ast.AST, scope: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                inner = scope + (child.name,)
                out[id(child)] = ".".join(inner)
                walk(child, inner)
            else:
                out[id(child)] = ".".join(scope)
                walk(child, scope)

    out[id(tree)] = ""
    walk(tree, ())
    return out


def _enclosing(node: ast.AST, qualnames: dict[int, str]) -> str:
    return qualnames.get(id(node), "")


def _class_names_in(node: ast.expr) -> set[str]:
    """isinstance 두 번째 인자에서 클래스 이름을 모은다 (튜플/리스트/집합 포함)."""
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        found: set[str] = set()
        for element in node.elts:
            found |= _class_names_in(element)
        return found
    return set()


def _subject_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _source_files() -> list[Path]:
    return sorted(_SRC.rglob("*.py"))


def scan_isinstance() -> list[tuple[str, int, str, str]]:
    """(모듈, 줄, qualname, 걸린 클래스 이름들) 목록."""
    sites: list[tuple[str, int, str, str]] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        qualnames = _qualname_map(tree)
        module = _module_name(path)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "isinstance" or len(node.args) != 2:
                continue
            hit = _class_names_in(node.args[1]) & COMPONENT_CLASS_NAMES
            if not hit:
                continue
            sites.append((module, node.lineno, _enclosing(node, qualnames),
                          ",".join(sorted(hit))))
    return sites


def scan_fsm_isinstance() -> list[tuple[str, int, str, str]]:
    """③ FSM·전략·훅 핸들러·Tool 클래스 대상 사이트 — ①과 같은 규칙, 다른 이름 집합."""
    sites: list[tuple[str, int, str, str]] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        qualnames = _qualname_map(tree)
        module = _module_name(path)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "isinstance" or len(node.args) != 2:
                continue
            hit = _class_names_in(node.args[1]) & FSM_CLASS_NAMES
            if not hit:
                continue
            sites.append((module, node.lineno, _enclosing(node, qualnames),
                          ",".join(sorted(hit))))
    return sites


def scan_shape_attrs() -> list[tuple[str, int, str, str]]:
    """(모듈, 줄, qualname, 속성 이름) 목록."""
    sites: list[tuple[str, int, str, str]] = []
    for path in _source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        qualnames = _qualname_map(tree)
        module = _module_name(path)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id not in {"getattr", "hasattr"} or len(node.args) < 2:
                continue
            attr = node.args[1]
            if not (isinstance(attr, ast.Constant) and isinstance(attr.value, str)):
                continue
            if attr.value not in SHAPE_ATTRS:
                continue
            if _subject_name(node.args[0]) in SHAPE_EXCLUDED_SUBJECTS:
                continue
            sites.append((module, node.lineno, _enclosing(node, qualnames), attr.value))
    return sites


def _apply_exemptions(sites, exempt: dict[str, str]):
    return [s for s in sites if f"{s[0]}::{s[2]}" not in exempt]


def _report(sites) -> str:
    return "\n".join(
        f"  {module}:{line} ({qualname or '<module>'}) → {what}"
        for module, line, qualname, what in sites[:40]
    )


# ─────────────────────────── ① isinstance 래칫 ───────────────────────────

def test_isinstance_on_component_classes_does_not_grow():
    sites = _apply_exemptions(scan_isinstance(), ISINSTANCE_EXEMPT)
    files = {module for module, _line, _qual, _what in sites}
    assert len(sites) <= RATCHET["isinstance_sites"], (
        f"컴포넌트 클래스 대상 isinstance가 {len(sites)}건으로 늘었다 "
        f"(기준선 {RATCHET['isinstance_sites']}). 종류를 타입으로 묻지 말고 "
        f"능력 메서드로 물어라:\n" + _report(sites)
    )
    assert len(files) <= RATCHET["isinstance_files"], (
        f"isinstance 분기가 {len(files)}개 파일로 퍼졌다 "
        f"(기준선 {RATCHET['isinstance_files']}):\n" + _report(sites)
    )


def test_isinstance_ratchet_baseline_is_not_stale():
    """기준선이 실측보다 크게 남아 있으면 내려라 — 래칫은 조여야 의미가 있다."""
    sites = _apply_exemptions(scan_isinstance(), ISINSTANCE_EXEMPT)
    files = {module for module, _line, _qual, _what in sites}
    assert RATCHET["isinstance_sites"] == len(sites), (
        f"기준선({RATCHET['isinstance_sites']})과 실측({len(sites)})이 다르다 — "
        f"RATCHET['isinstance_sites']를 {len(sites)}로 내려 잠가라."
    )
    assert RATCHET["isinstance_files"] == len(files), (
        f"기준선({RATCHET['isinstance_files']})과 실측({len(files)})이 다르다 — "
        f"RATCHET['isinstance_files']를 {len(files)}로 내려 잠가라."
    )


# ─────────────────────────── ② 형상 getattr 래칫 ───────────────────────────

def test_component_shape_getattr_does_not_grow():
    sites = _apply_exemptions(scan_shape_attrs(), SHAPE_ATTR_EXEMPT)
    files = {module for module, _line, _qual, _what in sites}
    assert len(sites) <= RATCHET["shape_attr_sites"], (
        f"컴포넌트 형상 getattr/hasattr가 {len(sites)}건으로 늘었다 "
        f"(기준선 {RATCHET['shape_attr_sites']}). 문자열로 형상을 더듬는 대신 "
        f"모델이 선언한 능력을 불러라:\n" + _report(sites)
    )
    assert len(files) <= RATCHET["shape_attr_files"], (
        f"형상 조회가 {len(files)}개 파일로 퍼졌다 "
        f"(기준선 {RATCHET['shape_attr_files']}):\n" + _report(sites)
    )


def test_shape_attr_ratchet_baseline_is_not_stale():
    sites = _apply_exemptions(scan_shape_attrs(), SHAPE_ATTR_EXEMPT)
    files = {module for module, _line, _qual, _what in sites}
    assert RATCHET["shape_attr_sites"] == len(sites), (
        f"기준선({RATCHET['shape_attr_sites']})과 실측({len(sites)})이 다르다 — "
        f"RATCHET['shape_attr_sites']를 {len(sites)}로 내려 잠가라."
    )
    assert RATCHET["shape_attr_files"] == len(files), (
        f"기준선({RATCHET['shape_attr_files']})과 실측({len(files)})이 다르다 — "
        f"RATCHET['shape_attr_files']를 {len(files)}로 내려 잠가라."
    )


# ────────────────── ③ FSM·전략·훅·Tool isinstance 래칫 ──────────────────

def test_isinstance_on_fsm_classes_does_not_grow():
    sites = _apply_exemptions(scan_fsm_isinstance(), FSM_ISINSTANCE_EXEMPT)
    files = {module for module, _line, _qual, _what in sites}
    assert len(sites) <= RATCHET["fsm_isinstance_sites"], (
        f"FSM·전략·훅·Tool 클래스 대상 isinstance가 {len(sites)}건으로 늘었다 "
        f"(기준선 {RATCHET['fsm_isinstance_sites']}). 새 병렬 사다리를 만들지 말고 "
        f"singledispatch(기저 폴백이 옳을 때)나 명시 레지스트리(누락이 에러여야 "
        f"할 때)를 써라:\n" + _report(sites)
    )
    assert len(files) <= RATCHET["fsm_isinstance_files"], (
        f"FSM 분기가 {len(files)}개 파일로 퍼졌다 "
        f"(기준선 {RATCHET['fsm_isinstance_files']}):\n" + _report(sites)
    )


def test_fsm_isinstance_ratchet_baseline_is_not_stale():
    sites = _apply_exemptions(scan_fsm_isinstance(), FSM_ISINSTANCE_EXEMPT)
    files = {module for module, _line, _qual, _what in sites}
    assert RATCHET["fsm_isinstance_sites"] == len(sites), (
        f"기준선({RATCHET['fsm_isinstance_sites']})과 실측({len(sites)})이 다르다 — "
        f"RATCHET['fsm_isinstance_sites']를 {len(sites)}로 내려 잠가라."
    )
    assert RATCHET["fsm_isinstance_files"] == len(files), (
        f"기준선({RATCHET['fsm_isinstance_files']})과 실측({len(files)})이 다르다 — "
        f"RATCHET['fsm_isinstance_files']를 {len(files)}로 내려 잠가라."
    )


def test_wp11_ladders_are_gone():
    """WP-11이 걷은 네 사다리가 **다시 자라지 않는지** — 이름으로 못 박는다.

    수만 보면 다른 자리가 늘고 이 자리가 줄어도 통과한다. 걷은 자리를 이름으로
    적어 두면 그 파일에 사다리가 돌아오는 순간 실패한다.
    """
    modules = {module for module, _l, _q, _w in scan_fsm_isinstance()}
    for gone in (
        "compiler.emit.sections",        # 상태·전략·트리거 서술
        "compiler.emit.agent_sections",  # legacy 에이전트 변형
        "view.editors.hook_panel",       # 훅 핸들러 폼(구성·저장)
        "view.editors.hook_handler_form",
        "view.canvas.node_item",         # 의사 상태 스타일
        "view.graph_io",                 # 프로젝트 캔버스 제외 규칙
    ):
        assert gone not in modules, f"{gone}에 종류 사다리가 돌아왔다"


# ─────────────────────────── 스캐너 자기 검증 ───────────────────────────

def test_exemptions_carry_a_reason():
    """면제는 사유를 강제한다 — 빈 사유는 '왜 남았는지'를 지운다."""
    for table in (ISINSTANCE_EXEMPT, SHAPE_ATTR_EXEMPT, FSM_ISINSTANCE_EXEMPT):
        for key, reason in table.items():
            assert reason.strip(), f"{key}: 면제 사유가 비었다"


def test_exemptions_point_at_live_sites():
    """존재하지 않는 자리를 면제로 붙잡고 있지 않은지 — 목록은 줄어들기만 한다."""
    live_isinstance = {f"{m}::{q}" for m, _l, q, _w in scan_isinstance()}
    live_shape = {f"{m}::{q}" for m, _l, q, _w in scan_shape_attrs()}
    live_fsm = {f"{m}::{q}" for m, _l, q, _w in scan_fsm_isinstance()}
    stale = sorted(set(ISINSTANCE_EXEMPT) - live_isinstance)
    stale += sorted(set(SHAPE_ATTR_EXEMPT) - live_shape)
    stale += sorted(set(FSM_ISINSTANCE_EXEMPT) - live_fsm)
    assert not stale, f"사라진 자리를 면제가 붙잡고 있다 — 목록에서 빼라: {stale}"


def test_scanner_sees_the_known_hotspots():
    """스캐너가 조용히 0을 세지 않는지 — 알려진 집중 지점을 확인한다."""
    modules = {module for module, _l, _q, _w in scan_isinstance()}
    # ①은 WP-10 이후 `kinds::spec_for` **한 자리**만 남았다(예정 면제) — 표적이
    # 하나뿐이라 그 하나를 건다. 지워지면 스캐너가 조용히 0을 세도 통과한다.
    assert "model.plugin.kinds" in modules
    shape_modules = {module for module, _l, _q, _w in scan_shape_attrs()}
    # WP-2b가 `model.project`를, WP-2c가 `compiler.emit.sections`를 비웠다 —
    # 같은 이유로 남은 집중 지점(WP-8·프론트매터 패널 소관)으로 교체한다.
    fsm_modules = {module for module, _l, _q, _w in scan_fsm_isinstance()}
    # WP-11 이후 ③의 집중 지점은 검증 규칙과 FSM 직렬화의 **구조 순회**다.
    assert "model.validation.machine_rules" in fsm_modules
    assert "model.serialize.ser" in fsm_modules
    assert "mcp.tools.query" in shape_modules
    assert "view.editors.frontmatter_panel" in shape_modules


def test_shape_exclusion_rule_is_applied():
    """제외 규칙이 실제로 무언가를 걸러내는지 (규칙이 죽으면 기준선이 튄다)."""
    excluded = [
        node
        for path in _source_files()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"getattr", "hasattr"}
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and node.args[1].value in SHAPE_ATTRS
        and _subject_name(node.args[0]) in SHAPE_EXCLUDED_SUBJECTS
    ]
    assert excluded, "제외 규칙이 하나도 걸러내지 않는다 — 규칙이 죽었다"
