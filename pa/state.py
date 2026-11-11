"""사용자 상태 (제외한 과제, 완료한 강의, 소요 시간 조정) — data/state.json 에 저장."""
import json

from pa.config import ROOT

PATH = ROOT / "data" / "state.json"


def load():
    st = json.loads(PATH.read_text()) if PATH.exists() else {}
    for k in ("ignored", "done", "minutes", "manual"):
        st.setdefault(k, {})
    return st


def save(state):
    PATH.parent.mkdir(exist_ok=True)
    PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2))
