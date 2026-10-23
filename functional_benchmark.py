
import csv
import glob
import importlib.util
import json
import os
import subprocess
import sys
from collections import defaultdict

ROOT = os.environ["BENCH_RESULTS"]
DETAIL_CSV = os.path.join(ROOT, "functional_results_v2.csv")
SUMMARY_CSV = os.path.join(ROOT, "functional_summary_v2.csv")

# Cada caso se ejecuta en un proceso Python independiente.
# No se inyectan imports ni se corrige el cÃ³digo generado.
CASES = {
    "01_lru": {
        "basic": '''
c = module.LRUCache(2)
c.put("a", 1)
assert c.get("a") == 1
''',
        "eviction": '''
c = module.LRUCache(2)
c.put("a", 1)
c.put("b", 2)
c.put("c", 3)
assert c.get("a") is None
assert c.get("b") == 2
assert c.get("c") == 3
''',
        "recency": '''
c = module.LRUCache(2)
c.put("a", 1)
c.put("b", 2)
assert c.get("a") == 1
c.put("c", 3)
assert c.get("b") is None
assert c.get("a") == 1
''',
        "update": '''
c = module.LRUCache(2)
c.put("a", 1)
c.put("b", 2)
c.put("a", 10)
c.put("c", 3)
assert c.get("a") == 10
assert c.get("b") is None
'''
    },

    "02_ttl": {
        "basic": '''
now = [0.0]
c = module.TTLCache(2, 10, clock=lambda: now[0])
c.put("a", 1)
assert c.get("a") == 1
''',
        "before_expiry": '''
now = [0.0]
c = module.TTLCache(2, 10, clock=lambda: now[0])
c.put("a", 1)
now[0] = 9.999
assert c.get("a") == 1
''',
        "expiry_boundary": '''
now = [0.0]
c = module.TTLCache(2, 10, clock=lambda: now[0])
c.put("a", 1)
now[0] = 10.0
assert c.get("a") is None
''',
        "delete": '''
c = module.TTLCache(2, 10, clock=lambda: 0)
c.put("a", 1)
c.delete("a")
assert c.get("a") is None
''',
        "lru_eviction": '''
c = module.TTLCache(2, 10, clock=lambda: 0)
c.put("a", 1)
c.put("b", 2)
assert c.get("a") == 1
c.put("c", 3)
assert c.get("b") is None
assert c.get("a") == 1
'''
    },

    "03_graph": {
        "shortest": '''
g = {
    "A": {"B": 1, "C": 4},
    "B": {"C": 2, "D": 5},
    "C": {"D": 1},
    "D": {}
}
assert module.shortest_path(g, "A", "D") == (
    4, ["A", "B", "C", "D"]
)
''',
        "same_node": '''
g = {"A": {"B": 2}, "B": {}}
assert module.shortest_path(g, "A", "A") == (0, ["A"])
''',
        "weighted": '''
g = {
    "A": {"B": 10, "C": 1},
    "C": {"B": 1},
    "B": {}
}
assert module.shortest_path(g, "A", "B") == (
    2, ["A", "C", "B"]
)
'''
    },

    "04_parser": {
        "simple": '''
assert module.parse_csv("a,b\\nc,d") == [
    ["a", "b"], ["c", "d"]
]
''',
        "quoted_comma": '''
assert module.parse_csv('"a,b",c') == [
    ["a,b", "c"]
]
''',
        "escaped_quotes": '''
assert module.parse_csv('"a""b",c') == [
    ['a"b', "c"]
]
''',
        "multiline": '''
assert module.parse_csv('"a\\nb",c') == [
    ["a\\nb", "c"]
]
''',
        "empty_fields": '''
assert module.parse_csv("a,,c") == [
    ["a", "", "c"]
]
''',
        "crlf": '''
assert module.parse_csv("a,b\\r\\nc,d") == [
    ["a", "b"], ["c", "d"]
]
'''
    },

    "05_scheduler": {
        "priority": '''
s = module.TaskScheduler()
s.add_task("low", 1, [])
s.add_task("high", 10, [])
assert s.next_task() == "high"
''',
        "dependency_block": '''
s = module.TaskScheduler()
s.add_task("A", 1, [])
s.add_task("B", 10, ["A"])
assert s.next_task() == "A"
''',
        "dependency_unlock": '''
s = module.TaskScheduler()
s.add_task("A", 1, [])
s.add_task("B", 10, ["A"])
assert s.next_task() == "A"
s.complete_task("A")
assert s.next_task() == "B"
''',
        "no_repeat_completed": '''
s = module.TaskScheduler()
s.add_task("A", 1, [])
assert s.next_task() == "A"
s.complete_task("A")
assert s.next_task() != "A"
''',
        "empty": '''
s = module.TaskScheduler()
assert s.next_task() is None
''',
        "multiple_dependencies": '''
s = module.TaskScheduler()
s.add_task("A", 1, [])
s.add_task("B", 2, [])
s.add_task("C", 10, ["A", "B"])
assert s.next_task() == "B"
s.complete_task("B")
assert s.next_task() == "A"
s.complete_task("A")
assert s.next_task() == "C"
'''
    }
}

CHILD = r'''
import importlib.util
import json
import sys
import traceback

path = sys.argv[1]
test_code = sys.argv[2]

try:
    spec = importlib.util.spec_from_file_location(
        "candidate", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    exec(test_code, {"module": module})
    result = {"status": "PASS", "error": ""}

except AssertionError:
    result = {
        "status": "FAIL",
        "error": traceback.format_exc(limit=2).strip()
    }
except Exception:
    result = {
        "status": "ERROR",
        "error": traceback.format_exc(limit=3).strip()
    }

print(json.dumps(result))
'''

rows = []
expected_files = 0

for mode in ("Base", "MTP4", "Ngram16"):
    for problem, tests in CASES.items():
        for repetition in (1, 2, 3):
            expected_files += 1
            filename = f"{mode}_{problem}_{repetition}.py"
            path = os.path.join(ROOT, filename)

            for test_name, code in tests.items():
                if not os.path.isfile(path):
                    status = "MISSING"
                    error = "Archivo no encontrado"
                else:
                    try:
                        proc = subprocess.run(
                            [sys.executable, "-c", CHILD, path, code],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )

                        if proc.returncode:
                            status = "ERROR"
                            error = proc.stderr.strip()[-800:]
                        else:
                            data = json.loads(proc.stdout.strip())
                            status = data["status"]
                            error = data["error"]

                    except subprocess.TimeoutExpired:
                        status = "TIMEOUT"
                        error = "Tiempo excedido: 5 segundos"
                    except Exception as exc:
                        status = "ERROR"
                        error = repr(exc)

                rows.append({
                    "mode": mode,
                    "problem": problem,
                    "repetition": repetition,
                    "test": test_name,
                    "status": status,
                    "error": error
                })

with open(DETAIL_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "mode", "problem", "repetition",
        "test", "status", "error"
    ])
    writer.writeheader()
    writer.writerows(rows)

summary = defaultdict(lambda: defaultdict(int))

for row in rows:
    key = (row["mode"], row["problem"])
    summary[key][row["status"]] += 1

summary_rows = []

for mode in ("Base", "MTP4", "Ngram16"):
    for problem in CASES:
        counts = summary[(mode, problem)]
        total = sum(counts.values())
        passed = counts["PASS"]

        summary_rows.append({
            "mode": mode,
            "problem": problem,
            "passed": passed,
            "failed": counts["FAIL"],
            "errors": counts["ERROR"],
            "timeouts": counts["TIMEOUT"],
            "missing": counts["MISSING"],
            "total": total,
            "percent": round(100 * passed / total, 2)
        })

with open(SUMMARY_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f, fieldnames=list(summary_rows[0])
    )
    writer.writeheader()
    writer.writerows(summary_rows)

print("\\nRESULTADOS POR MODELO")
print(f"{'MODELO':<10} {'PASS':>6} {'TOTAL':>7} {'PORCENTAJE':>12}")

for mode in ("Base", "MTP4", "Ngram16"):
    selected = [r for r in rows if r["mode"] == mode]
    passed = sum(r["status"] == "PASS" for r in selected)
    total = len(selected)
    print(
        f"{mode:<10} {passed:>6} {total:>7} "
        f"{100 * passed / total:>11.1f}%"
    )

print("\\nDETALLE POR PROBLEMA")
for row in summary_rows:
    print(
        f"{row['mode']:<8} {row['problem']:<13} "
        f"{row['passed']:>2}/{row['total']:<2} "
        f"({row['percent']:>5.1f}%)"
    )

print(f"\\nDetalle: {DETAIL_CSV}")
print(f"Resumen: {SUMMARY_CSV}")


