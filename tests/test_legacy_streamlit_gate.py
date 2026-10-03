"""The legacy UI must stop before its direct paid SDK and log paths."""

from __future__ import annotations

import ast
from contextlib import nullcontext
from pathlib import Path

import pytest

from legacy_streamlit_gate import SESSION_KEY, require_owner_session


TOKEN = "a" * 64


class Stopped(Exception):
    pass


class FakeStreamlit:
    def __init__(self, candidate="", submitted=False):
        self.session_state = {}
        self.candidate = candidate
        self.submitted = submitted
        self.errors = []
        self.forms = 0

    def error(self, message):
        self.errors.append(message)

    def stop(self):
        raise Stopped

    def form(self, name, *, clear_on_submit):
        assert name == "legacy_owner_login" and clear_on_submit
        self.forms += 1
        return nullcontext()

    def text_input(self, label, *, type):
        assert label == "Operator token" and type == "password"
        return self.candidate

    def form_submit_button(self, label):
        assert label == "Unlock private prototype"
        return self.submitted


def test_default_and_weak_token_stop_before_login():
    st = FakeStreamlit(TOKEN, submitted=True)
    with pytest.raises(Stopped):
        require_owner_session(st, {"ORALLEXA_UI_OWNER_TOKEN": TOKEN}, now=100)
    assert st.forms == 0 and SESSION_KEY not in st.session_state

    with pytest.raises(Stopped):
        require_owner_session(st, {
            "ORALLEXA_ENABLE_LEGACY_STREAMLIT": "1",
            "ORALLEXA_UI_OWNER_TOKEN": "short",
        }, now=100)
    assert st.forms == 0 and SESSION_KEY not in st.session_state


def test_wrong_token_stops_and_correct_token_grants_short_session():
    env = {"ORALLEXA_ENABLE_LEGACY_STREAMLIT": "1", "ORALLEXA_UI_OWNER_TOKEN": TOKEN}
    st = FakeStreamlit("wrong", submitted=True)
    with pytest.raises(Stopped):
        require_owner_session(st, env, now=100)
    assert SESSION_KEY not in st.session_state

    st.candidate = TOKEN
    require_owner_session(st, env, now=100)
    assert st.session_state[SESSION_KEY]["expires_at"] == 100 + 15 * 60
    assert TOKEN not in repr(st.session_state)

    st.candidate = ""
    st.submitted = False
    require_owner_session(st, env, now=999)
    assert st.forms == 2  # no new form once authenticated

    with pytest.raises(Stopped):
        require_owner_session(st, env, now=1000)
    assert SESSION_KEY not in st.session_state


def test_token_rotation_revokes_existing_streamlit_session():
    env = {"ORALLEXA_ENABLE_LEGACY_STREAMLIT": "1", "ORALLEXA_UI_OWNER_TOKEN": TOKEN}
    st = FakeStreamlit(TOKEN, submitted=True)
    require_owner_session(st, env, now=100)

    st.candidate = ""
    st.submitted = False
    with pytest.raises(Stopped):
        require_owner_session(st, {**env, "ORALLEXA_UI_OWNER_TOKEN": "b" * 64}, now=101)
    assert SESSION_KEY not in st.session_state


def test_gate_runs_before_models_and_broker_capable_brain_are_imported():
    source = Path(__file__).resolve().parents[1] / "app_ui.py"
    module = ast.parse(source.read_text(encoding="utf-8"))
    gate_line = next(node.lineno for node in module.body if isinstance(node, ast.Expr)
                     and isinstance(node.value, ast.Call)
                     and isinstance(node.value.func, ast.Name)
                     and node.value.func.id == "require_owner_session")
    dotenv_line = next(node.lineno for node in module.body if isinstance(node, ast.Expr)
                       and isinstance(node.value, ast.Call)
                       and isinstance(node.value.func, ast.Name)
                       and node.value.func.id == "load_dotenv")
    model_imports = [node.lineno for node in module.body if isinstance(node, ast.ImportFrom)
                     and node.module in {"openai", "core.brain", "llm.ui_analysis"}]
    model_imports += [node.lineno for node in module.body if isinstance(node, ast.Import)
                      and any(alias.name == "anthropic" for alias in node.names)]
    assert model_imports and dotenv_line < gate_line < min(model_imports)
