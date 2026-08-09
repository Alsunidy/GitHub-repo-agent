"""يولّد مخطط المعمارية من الـ graph المُصرَّف نفسه — لا يُرسم باليد.

    python scripts/export_architecture.py

المخرَج: docs/architecture.mmd — الصقه في mermaid.live لتصديره صورة للسلايد.
ميزة التوليد من الكود: المخطط لا يكذب على السلايد أبداً.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.graph.build import build_graph  # noqa: E402

out = ROOT / "docs" / "architecture.mmd"
out.parent.mkdir(exist_ok=True)
out.write_text(build_graph().get_graph().draw_mermaid(), encoding="utf-8")
print(f"كُتب: {out.relative_to(ROOT)}")
