"""
Integration test for full 2-tab automation workflow with AutomationWorker
"""

import asyncio
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from automation_worker import AutomationWorker
from mock_server import get_mock_server


async def test_full_workflow():
    print("Starting Mock Server...")
    mock_server = get_mock_server()
    mock_server.start()

    logs = []

    def handle_ui_event(event_type, data):
        if event_type == "log":
            line = data.get("line", "")
            logs.append(line)
            print(f"[UI LOG] {line}")
        elif event_type == "status":
            print(f"[UI STATUS] {data.get('status')}")
        elif event_type == "checklist":
            print(f"[UI CHECKLIST] {data}")

    worker = AutomationWorker(
        total_workflows=1,
        refresh_interval=2,
        otp_timeout=30,
        headless=True,
        target_url="http://127.0.0.1:5000/register",
        ui_callback=handle_ui_event
    )

    print("\n--- RUNNING WORKER ---")
    await worker.run()

    print("\n--- WORKER RUN COMPLETED ---")
    mock_server.stop()

    # Verify key steps took place
    log_text = " ".join(logs)
    assert "Created email" in log_text, "Should have created email"
    assert "Registration submitted" in log_text, "Should have submitted registration"
    assert "OTP requested" in log_text, "Should have requested OTP"
    assert "Refresh inbox #1" in log_text, "Should have refreshed inbox"
    assert "Account verified" in log_text, "Should have verified account"
    print("\n✓ ALL WORKFLOW ASSERTIONS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(test_full_workflow())
