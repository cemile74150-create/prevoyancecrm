"""
Extract Gravity Forms conditionalLogic blobs from local DOT/intranet dumps.

Writes:
  backend/offre_form_sources/conditional_logic/{gid}.json
  backend/offre_form_sources/manifest.json

Sources (read-only, outside the repo when needed):
  - Desktop/CRM demande d'offre/view-source_*.html  (Chrome view-source)
  - prevoyancecrm backend scripts/_tmp_gf14/*.html
  - prevoyancecrm backend/_clean_gf41.html
  - Tableau suivi/menage_rc_gf_dump.txt (HTML markers only — no JS blob)
"""
from __future__ import annotations

import html as html_lib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "offre_form_sources"
CL_DIR = OUT_DIR / "conditional_logic"
SCHEMAS = ROOT / "offre_form_schemas"

CRM_DUMPS = Path(r"C:\Users\offic\Desktop\CRM demande d'offre")
EXTRA_DUMPS = [
    Path(r"C:\Users\offic\Desktop\Cemile\Tableau suivi\prevoyancecrm\backend\scripts\_tmp_gf14\gf14_source.html"),
    Path(r"C:\Users\offic\Desktop\Cemile\Tableau suivi\prevoyancecrm\backend\scripts\_tmp_gf14\gf14_chat_latest.html"),
    Path(r"C:\Users\offic\Desktop\Cemile\Tableau suivi\prevoyancecrm\backend\_clean_gf41.html"),
    Path(r"C:\Users\offic\Desktop\Cemile\Tableau suivi\menage_rc_gf_dump.txt"),
]


def chrome_view_source_to_html(raw: str) -> str:
    parts = re.findall(r'<td class="line-content">(.*?)</td>', raw, re.I | re.S)
    text = "\n".join(parts) if parts else raw
    for _ in range(3):
        nxt = html_lib.unescape(text)
        if nxt == text:
            break
        text = nxt
    text = re.sub(
        r'<a class="html-attribute-value html-resource-link"[^>]*>(.*?)</a>',
        r"\1",
        text,
        flags=re.I | re.S,
    )
    text = re.sub(r'<span class="html-attribute-name">([^<]*)</span>', r"\1", text, flags=re.I)
    text = re.sub(r'<span class="html-attribute-value">([^<]*)</span>', r"\1", text, flags=re.I)
    text = re.sub(r'<span class="html-comment">&lt;!--(.*?)--&gt;</span>', r"<!--\1-->", text, flags=re.I | re.S)
    text = re.sub(r'<span class="html-doctype">&lt;!DOCTYPE html&gt;</span>', "<!DOCTYPE html>", text, flags=re.I)
    text = re.sub(r'<span class="html-doctype"><!DOCTYPE html></span>', "<!DOCTYPE html>", text, flags=re.I)
    text = re.sub(r'<span class="html-tag">', "", text, flags=re.I)
    text = re.sub(r"</span>", "", text, flags=re.I)
    text = re.sub(r'<div class="line-gutter-backdrop"></div>', "", text, flags=re.I)
    text = re.sub(r'<form autocomplete="off">.*?</form>', "", text, flags=re.I | re.S)
    return text


def load_html(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if 'class="line-content"' in raw or "line-gutter-backdrop" in raw:
        return chrome_view_source_to_html(raw)
    return raw


def extract_js_object_after(html: str, marker: str) -> str | None:
    i = html.find(marker)
    if i < 0:
        # tolerate quote variants after chrome decode
        alt = marker.replace("'", '"')
        i = html.find(alt)
    if i < 0:
        return None
    i = html.find("{", i)
    if i < 0:
        return None
    depth = 0
    for j, ch in enumerate(html[i:], i):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return html[i : j + 1]
    return None


def parse_conditional_logic(html: str, gid: int) -> dict[str, Any]:
    markers = [
        f"window['gf_form_conditional_logic'][{gid}]",
        f'window["gf_form_conditional_logic"][{gid}]',
        f"gf_form_conditional_logic'][{gid}]",
        f'gf_form_conditional_logic"][{gid}]',
    ]
    blob = None
    for marker in markers:
        blob = extract_js_object_after(html, marker)
        if blob:
            break
    if not blob:
        return {"gravity_form_id": gid, "fields": {}, "source": "missing"}

    fields: dict[str, Any] = {}
    for m in re.finditer(r'(\d+)\s*:\s*\{\s*"field"\s*:\s*\{', blob):
        fid = int(m.group(1))
        start = m.end() - 1
        depth = 0
        obj = None
        for j, ch in enumerate(blob[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(blob[start : j + 1])
                    except json.JSONDecodeError:
                        obj = None
                    break
        if not isinstance(obj, dict):
            continue
        if not obj.get("rules"):
            continue
        action = obj.get("actionType") or "show"
        if action != "show":
            # LeoSoft show_when only models "show when"; skip hide/other
            continue
        rules = []
        for r in obj.get("rules") or []:
            field_id = r.get("fieldId")
            if field_id is None:
                continue
            rules.append(
                {
                    "field": f"input_{field_id}",
                    "op": r.get("operator") or "is",
                    "value": r.get("value"),
                }
            )
        if not rules:
            continue
        fields[str(fid)] = {
            "logic": obj.get("logicType") or "all",
            "rules": rules,
            "enabled": obj.get("enabled", True),
        }

    dependents: dict[str, list[int]] = {}
    dm = re.search(r"dependents\s*:\s*(\{)", blob)
    if dm:
        dep_blob = extract_js_object_after(blob[dm.start() :], "dependents")
        if dep_blob:
            for em in re.finditer(r"(\d+)\s*:\s*\[([^\]]*)\]", dep_blob):
                dependents[em.group(1)] = [int(x) for x in re.findall(r"\d+", em.group(2))]

    return {
        "gravity_form_id": gid,
        "fields": fields,
        "dependents": dependents,
        "raw_blob_chars": len(blob),
    }


def html_conditional_markers(html: str, gid: int) -> dict[str, str]:
    """Fallback inventory: data-conditional-logic=hidden|visible per field id."""
    out: dict[str, str] = {}
    for m in re.finditer(
        rf'<(?:li|div|fieldset)([^>]*\bid="field_{gid}_(\d+)"[^>]*)>',
        html,
        re.I,
    ):
        attrs, fid = m.group(1), m.group(2)
        cm = re.search(r'data-conditional-logic=["\'](hidden|visible)["\']', attrs, re.I)
        if cm:
            out[fid] = cm.group(1).lower()
    return out


def schema_gid_map() -> dict[int, list[str]]:
    mapping: dict[int, list[str]] = {}
    for path in sorted(SCHEMAS.glob("*.json")):
        if path.name in {"index.json", "menu.json"}:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        gid = data.get("gravity_form_id")
        if isinstance(gid, int):
            mapping.setdefault(gid, []).append(path.stem)
    return mapping


def collect_source_files() -> list[Path]:
    files: list[Path] = []
    if CRM_DUMPS.exists():
        files.extend(sorted(CRM_DUMPS.glob("*.html")))
    for p in EXTRA_DUMPS:
        if p.exists():
            files.append(p)
    return files


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CL_DIR.mkdir(parents=True, exist_ok=True)

    by_gid: dict[int, dict[str, Any]] = {}
    sources_meta: list[dict[str, Any]] = []
    gid_schemas = schema_gid_map()

    for path in collect_source_files():
        html = load_html(path)
        gids = sorted({int(x) for x in re.findall(r"gform_wrapper_(\d+)", html)})
        if not gids:
            gids = sorted({int(x) for x in re.findall(r"gform_(\d+)", html)})
        entry = {
            "path": str(path),
            "name": path.name,
            "gravity_form_ids": gids,
            "has_gf_form_conditional_logic": "gf_form_conditional_logic" in html,
            "data_conditional_logic_count": len(re.findall(r"data-conditional-logic", html)),
        }
        sources_meta.append(entry)

        for gid in gids:
            parsed = parse_conditional_logic(html, gid)
            markers = html_conditional_markers(html, gid)
            parsed["html_markers"] = markers
            parsed["source_file"] = str(path)
            parsed["schema_ids"] = gid_schemas.get(gid, [])
            prev = by_gid.get(gid)
            # Prefer the dump with the most parsed field rules
            if prev is None or len(parsed.get("fields") or {}) > len(prev.get("fields") or {}):
                by_gid[gid] = parsed

    for gid, data in sorted(by_gid.items()):
        out = CL_DIR / f"{gid}.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Active schemas without a recovered JS blob
    missing = []
    for path in sorted(SCHEMAS.glob("*.json")):
        if path.name in {"index.json", "menu.json"}:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        fields = data.get("fields") or []
        if not fields:
            continue
        gid = data.get("gravity_form_id")
        cl = by_gid.get(gid) if isinstance(gid, int) else None
        n_rules = len((cl or {}).get("fields") or {})
        missing.append(
            {
                "schema_id": data.get("id") or path.stem,
                "gravity_form_id": gid,
                "fields_count": len(fields),
                "existing_show_when": sum(1 for f in fields if f.get("show_when")),
                "extracted_conditional_fields": n_rules,
                "has_js_blob": bool(n_rules),
                "html_markers": len((cl or {}).get("html_markers") or {}),
                "source_file": (cl or {}).get("source_file"),
            }
        )

    manifest = {
        "generated_by": "extract_gf_conditional_logic.py",
        "sources": sources_meta,
        "gravity_form_ids_extracted": sorted(by_gid.keys()),
        "conditional_logic_dir": "conditional_logic",
        "schema_coverage": missing,
        "notes": [
            "JS blob gf_form_conditional_logic is the reliable source of rules.",
            "data-conditional-logic=hidden|visible alone cannot recover parent/value rules.",
            "Forms with extracted_conditional_fields=0 still need a GF admin JSON export.",
        ],
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with_rules = sum(1 for g, d in by_gid.items() if d.get("fields"))
    print(f"sources={len(sources_meta)} gids={len(by_gid)} with_rules={with_rules}")
    print(f"wrote {CL_DIR}")
    print(f"wrote {OUT_DIR / 'manifest.json'}")


if __name__ == "__main__":
    main()
