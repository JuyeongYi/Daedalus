# WP-DM: 캔버스 드래그 이동 로직 통합

## 문제

캔버스의 이동 가능한 아이템 3종에 **공통 슈퍼클래스가 없다**. 각자 독립적으로
`_drag_start_pos` 기록 + 씬의 서로 다른 핸들러 호출을 중복 구현했고, 다중 선택
처리는 `StateNodeItem` 경로에만 있다.

| 아이템 | 베이스 | 드래그 필드 | 씬 핸들러 | 다중 선택 |
|---|---|---|---|---|
| `StateNodeItem` (node_item.py:36) | `QGraphicsItem` | `_drag_start_pos` | `handle_node_moved` | 지원(StateNodeItem만 수집) |
| `ReferenceNodeItem` (ref_node_item.py:22) | `QGraphicsItem` | `_drag_start_pos` | `handle_ref_node_moved` | **없음** |
| `WaypointHandleItem` (edge_item.py:329) | `QGraphicsEllipseItem` | `_drag_start` | `handle_waypoint_moved` | **없음** |

러버밴드 다중 선택이 도입된 뒤(캔버스 뷰 `RubberBandDrag`) 증상이 드러났다.
Qt는 선택된 이동 가능 아이템을 **전부 함께 화면에서 움직이지만**, release 이벤트는
**잡은 아이템 하나에만** 배달된다. 따라서:

- **일반 노드를 잡으면**: 함께 선택된 상태 노드는 MacroCommand로 묶이지만,
  함께 선택된 레퍼런스 노드·웨이포인트는 화면만 움직이고 VM에 반영되지 않는다.
- **레퍼런스 노드를 잡으면**: 자기 것만 커맨드가 되고 나머지는 전부 유실.
- **웨이포인트를 잡으면**: 마찬가지.

사용자 보고: "드래그 한 상태에서 레퍼런스 노드를 움직일때, 레퍼런스 노드가 아닌 것을
움직일 때 동작이 다르다.", "웨이포인트도 마찬가지임. 이동 관련 공통 로직이 없는 느낌임."

## 목표

무엇을 잡든 **선택된 모든 이동 가능 아이템이 함께 이동하고, 하나의 undo 단위가 된다.**

## 설계

### 1. 공통 믹스인 — `daedalus/view/canvas/draggable.py` (신규)

```python
class DraggableItemMixin:
    """캔버스에서 드래그 이동 가능한 아이템의 공통 로직.

    서브클래스는 자신의 mousePressEvent/mouseReleaseEvent에서
    begin_drag()/end_drag()를 호출하고, vm_position()/make_move_command()를 구현한다.
    """
```

제공(구상):
- `begin_drag() -> None` — 현재 `pos()`를 드래그 시작 좌표로 기록
- `end_drag() -> None` — 시작 좌표가 있고 실제로 움직였으면
  `scene.handle_items_moved(self, old, new)` 호출 후 시작 좌표 초기화.
  씬이 없거나 `handle_items_moved`가 없으면 `fallback_apply_move(new)` 호출(아래).
- `drag_origin() -> QPointF | None`

구현 요구(추상 — 서브클래스가 반드시 구현):
- `vm_position() -> QPointF` — **VM에 저장된 현재 좌표**(화면 좌표가 아니라).
  함께 드래그된 아이템의 "구 위치"를 이것으로 판정한다.
- `make_move_command(old: QPointF, new: QPointF) -> Command | None` —
  자기 타입에 맞는 이동 커맨드 생성. 만들 수 없으면 None.

`ABC`를 쓰지 말 것 — Qt 메타클래스와 충돌한다. `NotImplementedError`를 던지는
평범한 메서드로 두고, 믹스인은 `QGraphicsItem` 계열 앞에 둔다
(`class StateNodeItem(DraggableItemMixin, QGraphicsItem)`).

`fallback_apply_move(new)`는 기본 구현 no-op. `ReferenceNodeItem`이 기존
"씬 없을 때 ref_vm.x/y 직접 설정" 폴백을 유지하는 데 쓴다.

### 2. 씬의 단일 진입점 — `FsmScene.handle_items_moved`

```python
def handle_items_moved(self, grabbed, old_pos: QPointF, new_pos: QPointF) -> None:
```

동작:
1. `self.selectedItems()`에서 `DraggableItemMixin` 인스턴스를 수집.
   `grabbed`가 선택 목록에 없으면(Qt가 선택하지 않은 아이템을 드래그한 경우) 추가.
2. 각 아이템에 대해:
   - `grabbed`이면 `(old_pos, new_pos)`
   - 아니면 `(item.vm_position(), item.pos())`, 두 값이 같으면 **건너뜀**
   - `item.make_move_command(old, new)` — None이면 건너뜀
3. 커맨드 0개면 아무것도 안 함, 1개면 그대로 `execute`,
   2개 이상이면 `MacroCommand(children=cmds, description="캔버스 다중 이동")`으로 실행.

**아이템 타입 분기를 씬에 두지 말 것** — 커맨드 생성 지식은 각 아이템의
`make_move_command`에 있다. 씬은 수집·묶기만 한다.

### 3. 기존 세 핸들러 — 얇은 래퍼로 존치

`handle_node_moved` / `handle_ref_node_moved` / `handle_waypoint_moved`는
**시그니처를 바꾸지 말고** 내부에서 `handle_items_moved`에 위임한다
(기존 테스트·호출부 호환). `handle_waypoint_moved`는 `(edge, index, old, new)`를
받으므로 해당 핸들 아이템을 찾아 위임하거나, 단일 커맨드 경로를 유지해도 된다 —
다만 **핸들이 직접 호출하는 경로는 `handle_items_moved`를 거쳐야 한다.**

### 4. 각 아이템의 구현

- **`StateNodeItem`**: `vm_position()` → `QPointF(self.state_vm.x, self.state_vm.y)`,
  `make_move_command()` → `MoveStateCmd(self.state_vm, old_x=…, …)`
- **`ReferenceNodeItem`**: `vm_position()` → `QPointF(self.ref_vm.x, self.ref_vm.y)`,
  `make_move_command()` → `MoveRefCmd(…, sync_fn=scene._sync_refs_to_model)`.
  씬에서 `sync_fn`을 얻어야 한다 — 씬이 없으면 None 반환.
- **`WaypointHandleItem`**: `vm_position()` → `QPointF(*transition_vm.waypoints[index])`
  (인덱스 범위 밖이면 `self.pos()` 반환 — 방어),
  `make_move_command()` → `MoveWaypointCmd(transition_vm, index, …)`.
  **주의: 핸들 좌표계 확인 필수** — 핸들이 엣지의 자식이면 `pos()`가 씬 좌표와
  다를 수 있다. `_sync_handles`가 `handle.setPos(QPointF(*waypoints[i]))`로
  설정하므로 waypoints와 `pos()`는 같은 좌표계여야 한다. 실제로 확인하고,
  다르면 변환을 넣을 것.

### 5. 회귀 방지 — 반드시 지킬 기존 동작

- **웨이포인트 점프 버그 재발 금지**: `WaypointHandleItem.mousePressEvent`/
  `mouseReleaseEvent`의 `super()` 호출을 **제거하지 말 것**. Qt의 드래그 기준
  좌표가 사라져 다음 드래그가 좌상단으로 튄다(이미 한 번 겪은 버그, 회귀 테스트 있음).
- **핸들은 항상 보이고 비활성 시 흐려진다**(`setVisible(False)` 금지 — 마우스 그랩이
  죽는다). 기존 정책 테스트 있음.
- 삭제 키 처리에서 웨이포인트 핸들 우선 규칙 유지.

## 테스트 (필수)

`tests/view/canvas/test_drag_move.py` (신규). 오프스크린 + **실제 마우스 이벤트**로
검증할 것 — `QTest`/직접 `setPos` 호출은 이 버그를 못 잡는다(전례: 합성 이벤트가
실제 경로를 우회해 통과했다). `QMouseEvent`를 뷰포트에 `QApplication.sendEvent`로
보내는 방식을 쓸 것(`tests/view/canvas/test_canvas_interaction.py`의 기존 패턴 참조).

1. **혼합 다중 선택 드래그 — 잡은 대상 무관 동일 결과**:
   상태 노드 2 + 레퍼런스 노드 2 + 웨이포인트 1을 전부 선택하고,
   ① 상태 노드를 잡아 드래그 ② 레퍼런스 노드를 잡아 드래그 ③ 웨이포인트를 잡아 드래그 —
   **세 경우 모두** 선택된 모든 아이템의 VM 좌표가 같은 델타만큼 이동해야 한다.
2. **1회 undo로 전부 복원**: 위 각 경우에서 `undo()` 한 번에 모든 VM 좌표가 원위치.
3. **레퍼런스 모델 동기화**: 혼합 드래그 후 `project.reference_placements`의 좌표가
   갱신되고, undo 후 되돌아온다.
4. **단일 선택 회귀**: 아이템 하나만 선택해 드래그하면 기존과 동일하게
   단일 커맨드(MacroCommand 아님)가 쌓인다.
5. 기존 웨이포인트 점프 회귀 테스트·핸들 가시성 테스트가 계속 통과.

## 제약

- `python -m pytest tests/ -q` 전체 통과 (현재 1275 passed + 1 skipped).
  **컴파일러 출력은 한 바이트도 바뀌면 안 된다**(view 전용 변경).
- PySide6만 사용 (PyQt6 import 금지 — 설치돼 있지 않다).
- 커밋 메시지 한국어, 마지막 줄 빈 줄 뒤
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- 브랜치 `wp-dm`에서 작업.
