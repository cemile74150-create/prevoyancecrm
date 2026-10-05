import { randomUUID } from "crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  readdirSync,
  unlinkSync,
} from "fs";
import path from "path";
import type {
  AnalyseInput,
  AnalyseRecord,
  AnalyseResults,
  AnalyseStatus,
} from "./types";
import { emptyAnalyseInput } from "./types";

const DATA_DIR = path.join(process.cwd(), "data", "analyses");

function ensureDir() {
  if (!existsSync(DATA_DIR)) {
    mkdirSync(DATA_DIR, { recursive: true });
  }
}

function filePath(id: string) {
  return path.join(DATA_DIR, `${id}.json`);
}

export interface AnalyseListItem {
  id: string;
  createdAt: string;
  updatedAt: string;
  clientId: string | null;
  clientName: string;
  conseillerNom: string;
  status: AnalyseStatus;
  ville: string;
  hasResults: boolean;
}

/**
 * Persistance locale fichier JSON (Try Live — pas de CRM prod).
 */
export class AnalyseStore {
  list(): AnalyseRecord[] {
    ensureDir();
    return readdirSync(DATA_DIR)
      .filter((f) => f.endsWith(".json"))
      .map((f) => this.readFile(path.join(DATA_DIR, f)))
      .filter((r): r is AnalyseRecord => r != null)
      .map((r) => this.normalize(r))
      .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  }

  listSummaries(filter?: {
    clientId?: string | null;
  }): AnalyseListItem[] {
    return this.list()
      .filter((r) =>
        filter?.clientId != null ? r.clientId === filter.clientId : true,
      )
      .map((r) => ({
        id: r.id,
        createdAt: r.createdAt,
        updatedAt: r.updatedAt,
        clientId: r.clientId,
        clientName: `${r.input.client1.prenom} ${r.input.client1.nom}`.trim(),
        conseillerNom: r.input.conseillerNom || "",
        status: r.status,
        ville: r.input.villeRecherche,
        hasResults: !!r.results,
      }));
  }

  listByClient(clientId: string): AnalyseRecord[] {
    return this.list().filter((r) => r.clientId === clientId);
  }

  get(id: string): AnalyseRecord | null {
    ensureDir();
    const r = this.readFile(filePath(id));
    return r ? this.normalize(r) : null;
  }

  create(
    input?: Partial<AnalyseInput>,
    opts?: { clientId?: string | null; status?: AnalyseStatus },
  ): AnalyseRecord {
    ensureDir();
    const now = new Date().toISOString();
    const record: AnalyseRecord = {
      id: randomUUID(),
      createdAt: now,
      updatedAt: now,
      clientId: opts?.clientId ?? null,
      status: opts?.status ?? "brouillon",
      input: { ...emptyAnalyseInput(), ...input },
      results: null,
    };
    this.write(record);
    return record;
  }

  update(
    id: string,
    patch: {
      input?: AnalyseInput;
      results?: AnalyseResults | null;
      clientId?: string | null;
      status?: AnalyseStatus;
    },
  ): AnalyseRecord | null {
    const existing = this.get(id);
    if (!existing) return null;
    let status = patch.status ?? existing.status;
    if (patch.results && !patch.status) {
      status = "calculee";
    }
    const updated: AnalyseRecord = {
      ...existing,
      input: patch.input ?? existing.input,
      results: patch.results !== undefined ? patch.results : existing.results,
      clientId:
        patch.clientId !== undefined ? patch.clientId : existing.clientId,
      status,
      updatedAt: new Date().toISOString(),
    };
    this.write(updated);
    return updated;
  }

  delete(id: string): boolean {
    ensureDir();
    const p = filePath(id);
    if (!existsSync(p)) return false;
    unlinkSync(p);
    return true;
  }

  private normalize(r: AnalyseRecord): AnalyseRecord {
    return {
      ...r,
      clientId: r.clientId ?? null,
      status:
        r.status ??
        (r.results ? ("calculee" as AnalyseStatus) : ("brouillon" as AnalyseStatus)),
    };
  }

  private write(record: AnalyseRecord) {
    writeFileSync(filePath(record.id), JSON.stringify(record, null, 2), "utf8");
  }

  private readFile(p: string): AnalyseRecord | null {
    if (!existsSync(p)) return null;
    try {
      return JSON.parse(readFileSync(p, "utf8")) as AnalyseRecord;
    } catch {
      return null;
    }
  }
}

export const analyseStore = new AnalyseStore();
