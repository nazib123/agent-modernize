"""Quick test to verify Decimal/float patch works."""
import re
import tempfile
import subprocess
import sys
from pathlib import Path

code = Path("results/S1/S1_modern_service.py").read_text()
patched = re.sub(r"condecimal\([^)]*\)", "float", code)
patched = patched.replace(
    "from pydantic import BaseModel, constr, condecimal, conint",
    "from pydantic import BaseModel, constr, conint",
)

d = tempfile.mkdtemp()
Path(f"{d}/main.py").write_text(patched)
Path(f"{d}/test_q.py").write_text(
    f'import sys\nsys.path.insert(0, "{d}")\n'
    'from main import app\n'
    'from fastapi.testclient import TestClient\n'
    'c = TestClient(app)\n'
    'def test_ok():\n'
    '    r = c.post("/orders/validate-and-submit", json={"order_type":"NEW","account_id":"valid_account","account_status":"ACT","account_suspended":False,"past_due_amount":1.0,"past_due_threshold":500.0,"product_id":"valid_product","quantity":5,"min_order_qty":1,"max_order_qty":100,"discount_pct":10.0,"priority":"N","requested_due":"2026-05-15","order_date":"2026-05-04","current_balance":100.0,"credit_limit":10000.0,"tax_rate":8.25})\n'
    '    assert r.status_code == 200, f"Got {r.status_code}: {r.text}"\n'
)

r = subprocess.run(
    [sys.executable, "-m", "pytest", f"{d}/test_q.py", "-v", "--tb=short"],
    capture_output=True, text=True, cwd=d, timeout=30,
)
print(r.stdout[-500:])
if r.returncode != 0:
    print("STDERR:", r.stderr[-300:])
print(f"\nExit code: {r.returncode}")
