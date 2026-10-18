"""Write printable ArUco markers for the servo rig (D-008).

Marker id 1 → glue to the servo horn. Marker id 0 → fix next to the servo, same plane, as reference.
Print at 100% scale; ~25-30 mm squares work for a laptop webcam at 20-40 cm.

Usage: apps/api/.venv/Scripts/python scripts/make_aruco_markers.py [out_dir]
"""

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from integreat.observations.cv_angle import HORN_ID, REFERENCE_ID, marker_image  # noqa: E402

out = Path(sys.argv[1] if len(sys.argv) > 1 else "aruco_markers")
out.mkdir(parents=True, exist_ok=True)
sheet = []
for mid, name in [(REFERENCE_ID, "reference"), (HORN_ID, "horn")]:
    img = marker_image(mid, size=300, border=60)
    labelled = cv2.copyMakeBorder(img, 0, 50, 0, 0, cv2.BORDER_CONSTANT, value=255)
    cv2.putText(labelled, f"id {mid}: {name}", (60, labelled.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.9, 0, 2)
    cv2.imwrite(str(out / f"aruco_{mid}_{name}.png"), labelled)
    sheet.append(labelled)
cv2.imwrite(str(out / "aruco_sheet.png"), np.hstack(sheet))
print(f"wrote markers to {out.resolve()}")
