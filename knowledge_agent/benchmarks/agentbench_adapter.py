from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_DBBENCH_STEPS = [
    "read_schema",
    "generate_sql",
    "execute_sql",
    "validate_answer",
    "submit_answer",
]


@dataclass
class AgentBenchDBTask:
    task_id: str
    task: str
    context: dict[str, Any]
    benchmark_metadata: dict[str, Any]
    expected_steps: list[str]

    def to_project_task(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "domain": "agentbench_db",
            "task": self.task,
            "expected_steps": list(self.expected_steps),
            "expected_recovery_steps": list(self.context.get("expected_recovery_steps", [])),
            "required_before_report": ["read_schema", "execute_sql"],
            "context": self.context,
            "benchmark_metadata": self.benchmark_metadata,
            **self.context,
        }


class AgentBenchDBAdapter:
    """Adapter for AgentBench DBBench tasks.

    The official AgentBench repository is intentionally kept outside this
    project. This adapter tries to discover JSON/JSONL DBBench tasks in that
    external checkout and falls back to tiny sqlite smoke tasks only when the
    official data is not locally available.
    """

    def __init__(
        self,
        agentbench_root: str | Path = "external/AgentBench",
        split: str = "dev",
    ):
        self.agentbench_root = Path(agentbench_root)
        self.split = split

    def load_tasks(self, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
        tasks = self._load_official_like_tasks()
        if not tasks:
            tasks = self._fallback_tasks()
        if offset:
            tasks = tasks[offset:]
        if limit is not None:
            tasks = tasks[:limit]
        return [task.to_project_task() for task in tasks]

    def load_executable_tasks(self, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
        tasks = [
            task
            for task in self._load_official_like_tasks()
            if _gold_sql_matches_fixture(task.context)
        ]
        if not tasks:
            tasks = self._fallback_tasks()
        if offset:
            tasks = tasks[offset:]
        if limit is not None:
            tasks = tasks[:limit]
        return [task.to_project_task() for task in tasks]

    def to_agentbench_answer(self, result: Any) -> str:
        if hasattr(result, "trace") and result.trace and result.trace.result:
            return str(result.trace.result.result)
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False)
        return str(result)

    def official_score(self, project_task: dict[str, Any], final_answer: str) -> dict[str, Any]:
        metadata = project_task.get("benchmark_metadata") or {}
        context = project_task.get("context") or project_task
        expected = context.get("_private_expected_answer") or context.get("expected_answer")
        if isinstance(expected, list):
            expected = expected[0] if expected else None
        if expected is None:
            return {
                "official_score": None,
                "official_success": None,
                "scorer": "unavailable",
                "official_available": bool(metadata.get("official_available")),
            }
        normalized_answer = _normalize_answer(final_answer)
        normalized_expected = _normalize_answer(str(expected))
        success = normalized_expected in normalized_answer
        return {
            "official_score": 1.0 if success else 0.0,
            "official_success": success,
            "scorer": "local_expected_answer_match",
            "official_available": bool(metadata.get("official_available")),
        }

    def _load_official_like_tasks(self) -> list[AgentBenchDBTask]:
        if not self.agentbench_root.exists():
            return []
        candidates = self._candidate_files()
        tasks: list[AgentBenchDBTask] = []
        for path in candidates:
            for index, raw in enumerate(_read_json_records(path)):
                task = self._convert_official_record(raw, path, index)
                if task:
                    tasks.append(task)
        return tasks

    def _candidate_files(self) -> list[Path]:
        patterns = ["*db*dev*.jsonl", "*db*dev*.json", "*dbbench*.jsonl", "*dbbench*.json"]
        files: list[Path] = []
        for pattern in patterns:
            files.extend(self.agentbench_root.rglob(pattern))
        dbbench_dir = self.agentbench_root / "data" / "dbbench"
        files.extend([dbbench_dir / f"{self.split}.jsonl", dbbench_dir / f"{self.split}.json"])
        return sorted(
            {
                path
                for path in files
                if path.is_file()
                and ".git" not in path.parts
                and any(part.lower() in {"data", "tasks", "db", "dbbench"} for part in path.parts)
            }
        )

    def _convert_official_record(self, raw: dict[str, Any], path: Path, index: int) -> AgentBenchDBTask | None:
        prompt = _first_present(raw, ["description", "question", "query", "instruction", "task", "input"])
        if not prompt:
            return None
        task_id = str(_first_present(raw, ["id", "task_id", "idx", "qid"]) or f"{path.stem}_{index}")
        schema = _first_present(raw, ["schema", "db_schema", "database_schema", "add_description"]) or ""
        expected_answer = _first_present(raw, ["answer", "expected_answer", "gold", "label"])
        db_path = _first_present(raw, ["db_path", "database_path", "sqlite_path"])
        context = {
            "_private_official_record": raw,
            "official_record": _public_record(raw),
            "schema": schema,
            "db_path": db_path,
            "_private_expected_answer": expected_answer,
            "dbbench_fixture": _fixture_from_record(raw),
        }
        metadata = {
            "benchmark": "AgentBench",
            "environment": "dbbench",
            "split": self.split,
            "official_available": True,
            "official_task_id": task_id,
            "source_file": str(path),
        }
        return AgentBenchDBTask(task_id, str(prompt), context, metadata, list(DEFAULT_DBBENCH_STEPS))

    def _fallback_tasks(self) -> list[AgentBenchDBTask]:
        fixtures = [
            {
                "task_id": "dbbench_smoke_departments",
                "task": "Using the database schema, answer: Which department has the most employees?",
                "expected_answer": "Engineering",
                "schema": (
                    "departments(id INTEGER PRIMARY KEY, name TEXT); "
                    "employees(id INTEGER PRIMARY KEY, name TEXT, department_id INTEGER, salary INTEGER)"
                ),
                "tables": {
                    "departments": [
                        {"id": 1, "name": "Engineering"},
                        {"id": 2, "name": "Finance"},
                    ],
                    "employees": [
                        {"id": 1, "name": "Ada", "department_id": 1, "salary": 180000},
                        {"id": 2, "name": "Grace", "department_id": 1, "salary": 175000},
                        {"id": 3, "name": "Lin", "department_id": 2, "salary": 150000},
                    ],
                },
            },
            {
                "task_id": "dbbench_smoke_salary",
                "task": "Using SQL, answer: What is the highest salary in Engineering?",
                "expected_answer": "180000",
                "schema": (
                    "departments(id INTEGER PRIMARY KEY, name TEXT); "
                    "employees(id INTEGER PRIMARY KEY, name TEXT, department_id INTEGER, salary INTEGER)"
                ),
                "tables": {
                    "departments": [{"id": 1, "name": "Engineering"}],
                    "employees": [
                        {"id": 1, "name": "Ada", "department_id": 1, "salary": 180000},
                        {"id": 2, "name": "Grace", "department_id": 1, "salary": 175000},
                    ],
                },
            },
        ]
        tasks = []
        for fixture in fixtures:
            metadata = {
                "benchmark": "AgentBench",
                "environment": "dbbench",
                "split": self.split,
                "official_available": False,
                "official_task_id": fixture["task_id"],
                "blocked_reason": "official AgentBench DBBench data not discovered locally",
            }
            context = {
                "schema": fixture["schema"],
                "_private_expected_answer": fixture["expected_answer"],
                "dbbench_fixture": fixture,
            }
            tasks.append(
                AgentBenchDBTask(
                    task_id=fixture["task_id"],
                    task=fixture["task"],
                    context=context,
                    benchmark_metadata=metadata,
                    expected_steps=list(DEFAULT_DBBENCH_STEPS),
                )
            )
        return tasks


def execute_sql_fixture(fixture: dict[str, Any], sql: str) -> tuple[bool, str, list[dict[str, Any]]]:
    try:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        _load_fixture(connection, fixture)
        rows = connection.execute(sql).fetchall()
        output = [dict(row) for row in rows]
        return True, json.dumps(output, ensure_ascii=False), output
    except Exception as exc:  # pragma: no cover - exact sqlite errors vary
        return False, str(exc), []
    finally:
        try:
            connection.close()
        except Exception:
            pass


def heuristic_sql_for_task(task: str) -> str:
    lowered = task.lower()
    if "most employees" in lowered and "department" in lowered:
        return (
            "SELECT d.name FROM departments d JOIN employees e ON e.department_id = d.id "
            "GROUP BY d.id, d.name ORDER BY COUNT(*) DESC LIMIT 1"
        )
    if "highest salary" in lowered and "engineering" in lowered:
        return (
            "SELECT MAX(e.salary) AS highest_salary FROM employees e "
            "JOIN departments d ON e.department_id = d.id WHERE d.name = 'Engineering'"
        )
    return "SELECT 1 AS answer"


def _load_fixture(connection: sqlite3.Connection, fixture: dict[str, Any]) -> None:
    for table_name, rows in (fixture.get("tables") or {}).items():
        if not rows:
            continue
        columns = list(rows[0].keys())
        column_defs = ", ".join(f"{column} {_sqlite_type(rows[0][column])}" for column in columns)
        quoted_columns = [_quote_identifier(column) for column in columns]
        column_defs = ", ".join(
            f"{quoted_column} {_sqlite_type(rows[0][column])}"
            for quoted_column, column in zip(quoted_columns, columns)
        )
        connection.execute(f"CREATE TABLE {_quote_identifier(table_name)} ({column_defs})")
        placeholders = ", ".join("?" for _ in columns)
        connection.executemany(
            f"INSERT INTO {_quote_identifier(table_name)} ({', '.join(quoted_columns)}) VALUES ({placeholders})",
            [[row.get(column) for column in columns] for row in rows],
        )
    connection.commit()


def _sqlite_type(value: Any) -> str:
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "REAL"
    return "TEXT"


def _fixture_from_record(raw: dict[str, Any]) -> dict[str, Any]:
    fixture = raw.get("dbbench_fixture") or raw.get("fixture") or {}
    if isinstance(fixture, dict) and fixture:
        return fixture
    table = raw.get("table") or {}
    table_info = table.get("table_info") or {}
    columns = [column.get("name") for column in table_info.get("columns", []) if column.get("name")]
    rows = table_info.get("rows") or []
    table_name = table.get("table_name") or "main_table"
    converted_rows = []
    for row in rows:
        if isinstance(row, list) and len(row) == len(columns):
            converted_rows.append({column: row[index] for index, column in enumerate(columns)})
    if not converted_rows:
        return {}
    return {
        "schema": raw.get("add_description") or "",
        "tables": {table_name: converted_rows},
    }


def _gold_sql_matches_fixture(context: dict[str, Any]) -> bool:
    raw = context.get("_private_official_record") or {}
    sql = (raw.get("sql") or {}).get("query")
    expected = context.get("_private_expected_answer")
    fixture = context.get("dbbench_fixture") or {}
    if not sql or not expected or not fixture.get("tables"):
        return False
    expected_values = expected if isinstance(expected, list) else [expected]
    ok, content, _rows = execute_sql_fixture(fixture, sql)
    return ok and any(str(value) in content for value in expected_values)


def _public_record(raw: dict[str, Any]) -> dict[str, Any]:
    public = {key: value for key, value in raw.items() if key not in {"label", "answer", "expected_answer", "gold", "sql"}}
    table = public.get("table")
    if isinstance(table, dict):
        table = dict(table)
        table_info = dict(table.get("table_info") or {})
        table_info.pop("rows", None)
        table["table_info"] = table_info
        public["table"] = table
    return public


def _read_json_records(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return []
    records: list[dict[str, Any]] = []
    if path.suffix == ".jsonl":
        for line in text.splitlines():
            if line.strip():
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(item, dict):
                    records.append(item)
        return records
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ["data", "tasks", "examples"]:
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
        return [payload]
    return []


def _first_present(raw: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if raw.get(key) not in (None, ""):
            return raw[key]
    return None


def _normalize_answer(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'
