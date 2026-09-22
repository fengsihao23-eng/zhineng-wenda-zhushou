"""Exercise real process logging without replacing pytest's own handlers."""
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap


API_ROOT = Path(__file__).resolve().parents[1]


def without_timestamps(rows):
    # Each standard logging Handler formats independently; emission times may
    # differ by microseconds while the event and request fields must agree.
    assert all("timestamp" in row for row in rows)
    return [{key: value for key, value in row.items() if key != "timestamp"} for row in rows]


def run_logging_process(script, log_file):
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=API_ROOT,
        env={**os.environ, "LOG_FILE": str(log_file), "LOG_LEVEL": "INFO", "MODEL_PROVIDER": "fake"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def test_structlog_and_stdlib_write_json_stacktraces_and_respect_level_changes(tmp_path):
    log_file = tmp_path / "app.log"
    stdout = run_logging_process('''
        import logging
        import os
        from app.core.logging import setup_logging, get_logger, bind_context, clear_context

        setup_logging("INFO", os.environ["LOG_FILE"])
        logger = get_logger("business").bind(component="scores")
        bind_context(request_id="request-one")
        logger.info("business_event", score=664)
        logging.getLogger("legacy").warning("legacy %s", "event", extra={"student_id": "student-one"})
        try:
            raise ValueError("expected structured failure")
        except ValueError:
            logger.exception("business_failure")
            logging.getLogger("legacy").exception("legacy_failure")
        clear_context()
        setup_logging("ERROR", os.environ["LOG_FILE"])
        logger.info("suppressed_info")
        logging.getLogger("uvicorn.error").warning("suppressed_uvicorn_warning")
        logger.error("visible_error")
        setup_logging("DEBUG", os.environ["LOG_FILE"])
        logger.debug("visible_debug")
    ''', log_file)
    file_rows = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert without_timestamps(stdout) == without_timestamps(file_rows)
    events = {row["event"]: row for row in file_rows}
    assert events["business_event"]["request_id"] == "request-one"
    assert events["business_event"]["score"] == 664
    assert events["legacy event"]["request_id"] == "request-one"
    assert events["legacy event"]["student_id"] == "student-one"
    for event in ("business_failure", "legacy_failure"):
        assert "Traceback (most recent call last)" in events[event]["exception"]
        assert "ValueError: expected structured failure" in events[event]["exception"]
        assert "exc_info" not in events[event]
    assert "suppressed_info" not in events
    assert "suppressed_uvicorn_warning" not in events
    assert events["visible_debug"]["level"] == "debug"
    assert "request_id" not in events["visible_error"]
    assert all("timestamp" in row and "logger" in row for row in file_rows)


def test_request_context_is_isolated_and_errors_keep_their_request_id(tmp_path):
    log_file = tmp_path / "requests.log"
    rows = run_logging_process('''
        import asyncio
        import logging
        from httpx import ASGITransport, AsyncClient
        import structlog
        from app.main import app
        import app.main as main
        from app.core.logging import get_logger
        from app.core.rate_limit import RateLimiter

        @app.get("/test/log/{marker}")
        async def log_endpoint(marker: str):
            await asyncio.sleep(0)
            get_logger("business").info("inside_request", marker=marker)
            logging.getLogger("legacy").warning("inside_legacy_request", extra={"marker": marker})
            if marker == "broken":
                raise RuntimeError("expected endpoint failure")
            return {"marker": marker}

        async def check():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                responses = await asyncio.gather(client.get("/test/log/first"), client.get("/test/log/second"))
                assert all(response.status_code == 200 for response in responses)
                assert responses[0].headers["X-Request-ID"] != responses[1].headers["X-Request-ID"]
                broken = await client.get("/test/log/broken")
                assert broken.status_code == 500
                assert broken.json()["error"]["request_id"] == broken.headers["X-Request-ID"]
                assert broken.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
                assert "expected endpoint failure" not in broken.text
                main.rate_limiter = RateLimiter(1, 100)
                await client.get("/test/log/allowed")
                limited = await client.get("/test/log/limited")
                assert limited.status_code == 429
                assert limited.json()["error"]["request_id"] == limited.headers["X-Request-ID"]
                assert "request_id" not in structlog.contextvars.get_contextvars()
            get_logger("business").info("outside_request")
        asyncio.run(check())
    ''', log_file)
    assert without_timestamps(rows) == without_timestamps([json.loads(line) for line in log_file.read_text().splitlines()])
    completed = {row["path"]: row for row in rows if row["event"] == "request_completed"}
    for row in rows:
        if row["event"] in {"inside_request", "inside_legacy_request"}:
            path = f'/test/log/{row["marker"]}'
            assert row["request_id"] == completed[path]["request_id"]
            assert row["path"] == path
            assert row["method"] == "GET"
    failure = next(row for row in rows if row["event"] == "unhandled_exception")
    assert failure["request_id"] == completed["/test/log/broken"]["request_id"]
    assert "RuntimeError: expected endpoint failure" in failure["exception"]
    assert completed["/test/log/broken"]["status_code"] == 500
    assert completed["/test/log/limited"]["status_code"] == 429
    assert "request_id" not in next(row for row in rows if row["event"] == "outside_request")
