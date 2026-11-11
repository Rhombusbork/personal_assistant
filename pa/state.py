"""사용자 상태 (제외한 과제, 완료한 강의, 소요 시간 조정) — data/state.json 에 저장."""
import json

from pa.config import ROOT

PATH = ROOT / "data" / "state.json"


def load():
    if PATH.exists():
        return json.loads(PATH.read_text())
    return {"ignored": {}, "done": {}, "minutes": {}}


def save(state):
    PATH.parent.mkdir(exist_ok=True)
    PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2))
