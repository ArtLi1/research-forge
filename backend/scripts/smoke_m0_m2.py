"""Run a real milestone 0-2 smoke test against locally running services."""

import sys
import time
from pathlib import Path

import httpx
import pymupdf

API = "http://127.0.0.1:8000/api/v1"
PROJECT_A = "Milestone 0-2 验收 A"
PROJECT_B = "Milestone 0-2 验收 B"


def make_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Multi-hop UAV Computation Offloading", fontsize=18)
    page.insert_text((72, 110), "System Model", fontsize=15)
    page.insert_textbox(
        pymupdf.Rect(72, 140, 520, 195),
        (
            "In a post-disaster network, UAV relays forward computation tasks over multiple "
            "wireless hops to an edge server. The route selection mechanism minimizes delay "
            "while avoiding unavailable ground links."
        ),
        fontsize=11,
    )
    page.insert_text((72, 210), "Algorithm", fontsize=15)
    page.insert_textbox(
        pymupdf.Rect(72, 240, 520, 295),
        (
            "A lightweight shortest-path policy selects execution nodes and forwarding paths. "
            "Continuous power control and trajectory optimization are excluded."
        ),
        fontsize=11,
    )
    document.set_metadata({"title": "Multi-hop UAV Computation Offloading"})
    document.save(path)
    document.close()


def project(client: httpx.Client, name: str) -> dict:
    projects = client.get(f"{API}/projects").raise_for_status().json()
    existing = next((item for item in projects if item["name"] == name), None)
    if existing:
        return existing
    response = client.post(
        f"{API}/projects",
        json={
            "name": name,
            "description": "里程碑 0–2 自动验收项目",
            "research_goal": "检索灾后多跳计算卸载的路径机制",
            "preferences": {"algorithm_complexity": "low"},
            "exclusions": ["连续功率控制"],
        },
    )
    response.raise_for_status()
    return response.json()


def wait_for_task(client: httpx.Client, task_id: str) -> dict:
    for _ in range(300):
        task = client.get(f"{API}/tasks/{task_id}").raise_for_status().json()
        if task["status"] in {"succeeded", "partial"}:
            return task
        if task["status"] == "failed":
            raise RuntimeError(task.get("error") or "paper task failed")
        time.sleep(1)
    raise TimeoutError("paper task did not finish in 300 seconds")


def main() -> None:
    pdf_path = Path("data/smoke/multi-hop-uav-offloading.pdf")
    make_pdf(pdf_path)
    with httpx.Client(timeout=60, trust_env=False) as client:
        project_a = project(client, PROJECT_A)
        project_b = project(client, PROJECT_B)
        with pdf_path.open("rb") as file:
            upload = client.post(
                f"{API}/papers/upload",
                data={"project_id": project_a["id"]},
                files={"files": (pdf_path.name, file, "application/pdf")},
            )
        upload.raise_for_status()
        uploaded = upload.json()[0]
        paper_id = uploaded["paper"]["id"]
        if uploaded["task_id"]:
            wait_for_task(client, uploaded["task_id"])
        elif uploaded["paper"]["parse_status"] not in {"completed", "partial"}:
            task = client.post(f"{API}/papers/{paper_id}/reparse").raise_for_status().json()
            wait_for_task(client, task["id"])

        association = client.post(
            f"{API}/projects/{project_b['id']}/papers/{paper_id}",
            json={},
        )
        if association.status_code not in {204, 409}:
            association.raise_for_status()

        with pdf_path.open("rb") as file:
            duplicate = client.post(
                f"{API}/papers/upload",
                files={"files": (pdf_path.name, file, "application/pdf")},
            )
        duplicate.raise_for_status()
        assert duplicate.json()[0]["duplicate"] is True

        evidence = client.post(
            f"{API}/search",
            json={
                "query": "post-disaster multi-hop route selection mechanism",
                "scope": "project",
                "project_id": project_a["id"],
                "filters": {},
                "top_k": 5,
            },
        )
        evidence.raise_for_status()
        pack = evidence.json()
        assert pack["items"], pack
        project_paper_ids = {
            item["id"]
            for item in client.get(
                f"{API}/projects/{project_a['id']}/papers"
            ).raise_for_status().json()
        }
        assert all(item["paper_id"] in project_paper_ids for item in pack["items"])
        assert all(item["page_start"] for item in pack["items"])
        print(
            {
                "project_a": project_a["id"],
                "project_b": project_b["id"],
                "paper_id": paper_id,
                "duplicate": True,
                "evidence_count": len(pack["items"]),
            }
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"smoke failed: {exc}", file=sys.stderr)
        raise
