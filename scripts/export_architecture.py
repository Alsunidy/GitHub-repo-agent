"""Generate the architecture diagram from the compiled graph itself -- never by hand.

    python scripts/export_architecture.py

Output: docs/architecture.mmd -- paste it into mermaid.live to export an image
for the slide. Generating it from code means the diagram can never contradict
what the system actually does.
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.graph.build import build_graph  # noqa: E402

out = ROOT / "docs" / "architecture.mmd"
out.parent.mkdir(exist_ok=True)
out.write_text(build_graph().get_graph().draw_mermaid(), encoding="utf-8")
print(f"wrote: {out.relative_to(ROOT)}")
