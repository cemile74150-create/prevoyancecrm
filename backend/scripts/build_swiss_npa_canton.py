"""Build NPA -> canton map from the official swisstopo locality directory."""
from __future__ import annotations

import csv
import io
import json
import zipfile
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

URL = (
    "https://data.geo.admin.ch/ch.swisstopo-vd.ortschaftenverzeichnis_plz/"
    "ortschaftenverzeichnis_plz/ortschaftenverzeichnis_plz_2056.csv.zip"
)
OUT = Path(__file__).resolve().parents[1] / "data" / "swiss_npa_canton.json"


def main() -> None:
    raw = urllib.request.urlopen(URL, timeout=120).read()
    zf = zipfile.ZipFile(io.BytesIO(raw))
    csv_name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
    data = zf.read(csv_name)
    text = None
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise RuntimeError("Cannot decode CSV")
    sample = text.splitlines()[0]
    delim = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    fields = list(reader.fieldnames or [])
    print("fields:", fields)
    lower = {f.lower(): f for f in fields}

    def pick(*candidates: str) -> str:
        for cand in candidates:
            if cand in lower:
                return lower[cand]
        for key, original in lower.items():
            for cand in candidates:
                if cand in key:
                    return original
        raise KeyError(candidates)

    plz_key = pick("plz", "postleitzahl", "npa")
    canton_key = pick("kantonskürzel", "kantonskuerzel", "kanton", "canton")
    name_key = pick("ortschaftsname", "ortschaft", "langtext", "localite")

    by_npa: dict[str, Counter] = defaultdict(Counter)
    names_by_npa: dict[str, set[str]] = defaultdict(set)
    for row in reader:
        npa = str(row.get(plz_key) or "").strip()
        if npa.isdigit() and len(npa) == 4:
            pass
        elif npa.isdigit() and len(npa) < 4:
            npa = npa.zfill(4)
        else:
            continue
        canton = str(row.get(canton_key) or "").strip().upper()
        if not canton or canton == "FL":
            continue
        by_npa[npa][canton] += 1
        name = str(row.get(name_key) or "").strip()
        if name:
            names_by_npa[npa].add(name)

    mapping = {}
    ambiguous = {}
    for npa, counts in sorted(by_npa.items()):
        top = counts.most_common()
        mapping[npa] = top[0][0]
        if len(top) > 1 and top[0][1] == top[1][1]:
            ambiguous[npa] = [c for c, _ in top]

    payload = {
        "source": URL,
        "source_label": "swisstopo Official directory of towns and cities (PLZ)",
        "npa_to_canton": mapping,
        "ambiguous_npa": ambiguous,
        "localities": {npa: sorted(names) for npa, names in names_by_npa.items()},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", OUT, "npas", len(mapping), "ambiguous", len(ambiguous))
    for sample_npa in ("1200", "1201", "1000", "1003", "1950", "1211", "7500"):
        print(sample_npa, mapping.get(sample_npa), sorted(names_by_npa.get(sample_npa, []))[:5])


if __name__ == "__main__":
    main()
