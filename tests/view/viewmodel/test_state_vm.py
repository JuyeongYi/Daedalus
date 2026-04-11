from daedalus.model.fsm.state import SimpleState
from daedalus.model.fsm.transition import Transition
from daedalus.view.viewmodel.state_vm import StateViewModel, TransitionViewModel


class TestStateViewModel:
    def test_wraps_model(self):
        model = SimpleState(name="Idle")
        vm = StateViewModel(model=model)
        assert vm.model is model
        assert vm.model.name == "Idle"

    def test_default_position(self):
        vm = StateViewModel(model=SimpleState(name="s"))
        assert vm.x == 0.0
        assert vm.y == 0.0

    def test_default_size(self):
        vm = StateViewModel(model=SimpleState(name="s"))
        assert vm.width == 140.0
        assert vm.height == 60.0

    def test_default_not_selected(self):
        vm = StateViewModel(model=SimpleState(name="s"))
        assert vm.selected is False

    def test_position_mutable(self):
        vm = StateViewModel(model=SimpleState(name="s"))
        vm.x = 100.0
        vm.y = 200.0
        assert vm.x == 100.0
        assert vm.y == 200.0


class TestTransitionViewModel:
    def test_wraps_model_and_endpoints(self):
        s1 = SimpleState(name="A")
        s2 = SimpleState(name="B")
        model = Transition(source=s1, target=s2)
        vm_a = StateViewModel(model=s1)
        vm_b = StateViewModel(model=s2)
        tvm = TransitionViewModel(model=model, source_vm=vm_a, target_vm=vm_b)
        assert tvm.model is model
        assert tvm.source_vm is vm_a
        assert tvm.target_vm is vm_b

    def test_default_not_selected(self):
        s1 = SimpleState(name="A")
        s2 = SimpleState(name="B")
        tvm = TransitionViewModel(
            model=Transition(source=s1, target=s2),
            source_vm=StateViewModel(model=s1),
            target_vm=StateViewModel(model=s2),
        )
        assert tvm.selected is False
