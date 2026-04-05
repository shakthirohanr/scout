import type {
  ChallengeCatalogItem,
  CTFSourceSummary,
  ImportCTFInput,
  SteeringChallengeResult,
} from "@/lib/types";
import { revalidateTag, unstable_cache } from "next/cache";

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8081";
const CHALLENGE_CATALOG_TAG = "challenge-catalog";
const CTF_SOURCES_TAG = "ctf-sources";

export class BackendRequestError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "BackendRequestError";
    this.status = status;
  }
}

type BackendCatalogItem = {
  id: string;
  ctf_id: number;
  ctf_name: string;
  name: string;
  path: string;
  category: string;
  value: number;
  description: string;
  connection_info: string;
  has_distfiles: boolean;
  distfile_count: number;
  state: "idle" | "starting" | "running" | "solved" | "gave_up" | "cancelled" | "failed" | "finished";
  run_count: number;
  latest_run_id: string | null;
  current_run_id: string | null;
  latest_flag: string | null;
  latest_log_path: string | null;
  latest_trace_id: string | null;
  steering_log_path: string | null;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string | null;
};

type BackendCTFSourceSummary = {
  id: number;
  name: string;
  slug: string;
  base_url: string;
  auth_mode: string;
  challenges_root: string;
  challenge_count: number;
  last_import_at: string | null;
  last_import_status: string;
  last_import_error: string;
  created_at: string;
  updated_at: string;
};

type BackendCatalogResponse = {
  root: string;
  count: number;
  ctfs: BackendCTFSourceSummary[];
  catalog: BackendCatalogItem[];
  generated_at: string;
};

type BackendCTFListResponse = {
  ctfs: BackendCTFSourceSummary[];
  count: number;
  generated_at: string;
};

type BackendCTFImportResponse = {
  ctf: BackendCTFSourceSummary;
  imported_challenges: number;
  downloaded_files: number;
  root_directory: string;
  generated_at: string;
};

type BackendStartChallengeResponse = {
  challenge: BackendCatalogItem;
  run: Record<string, unknown> | null;
  generated_at: string;
};

type BackendKillChallengeResponse = {
  challenge: BackendCatalogItem;
  termination: {
    cancelled_runs: Record<string, unknown>[];
    cancelled_count: number;
    containers_removed: number;
  };
  generated_at: string;
};

type BackendDeleteChallengeResponse = {
  challenge: BackendCatalogItem;
  deleted_runs: number;
  files_removed: number;
  generated_at: string;
};

type BackendSteerChallengeResponse = {
  run_id: string;
  challenge_id: string;
  queued: string;
  source: string;
  created_at: string;
  generated_at: string;
};

function backendBaseUrl(): string {
  return process.env.BACKEND_API_URL?.trim() || DEFAULT_BACKEND_URL;
}

function toCatalogItem(item: BackendCatalogItem): ChallengeCatalogItem {
  return {
    id: item.id,
    ctfId: item.ctf_id,
    ctfName: item.ctf_name,
    name: item.name,
    path: item.path,
    category: item.category,
    value: item.value,
    description: item.description,
    connectionInfo: item.connection_info,
    hasDistfiles: item.has_distfiles,
    distfileCount: item.distfile_count,
    state: item.state,
    runCount: item.run_count,
    latestRunId: item.latest_run_id,
    currentRunId: item.current_run_id,
    latestFlag: item.latest_flag,
    latestLogPath: item.latest_log_path,
    latestTraceId: item.latest_trace_id,
    steeringLogPath: item.steering_log_path,
    startedAt: item.started_at,
    finishedAt: item.finished_at,
    updatedAt: item.updated_at,
  };
}

function toCTFSource(item: BackendCTFSourceSummary): CTFSourceSummary {
  return {
    id: item.id,
    name: item.name,
    slug: item.slug,
    baseUrl: item.base_url,
    authMode: item.auth_mode,
    challengesRoot: item.challenges_root,
    challengeCount: item.challenge_count,
    lastImportAt: item.last_import_at,
    lastImportStatus: item.last_import_status,
    lastImportError: item.last_import_error,
    createdAt: item.created_at,
    updatedAt: item.updated_at,
  };
}

async function fetchBackend<T>(pathname: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${backendBaseUrl()}${pathname}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    let message = body?.trim() || `Backend request failed: ${response.status} ${response.statusText}`;
    if (body) {
      try {
        const parsed = JSON.parse(body) as { detail?: string; error?: string };
        message = parsed.detail || parsed.error || message;
      } catch {}
    }
    throw new BackendRequestError(
      response.status,
      message,
    );
  }

  return (await response.json()) as T;
}

const getCachedChallengeCatalog = unstable_cache(
  async (): Promise<ChallengeCatalogItem[]> => {
    const payload = await fetchBackend<BackendCatalogResponse>("/api/v1/challenges");
    return payload.catalog.map(toCatalogItem);
  },
  ["challenge-catalog"],
  { revalidate: 5, tags: [CHALLENGE_CATALOG_TAG] },
);

const getCachedCTFs = unstable_cache(
  async (): Promise<CTFSourceSummary[]> => {
    const payload = await fetchBackend<BackendCTFListResponse>("/api/v1/ctfs");
    return payload.ctfs.map(toCTFSource);
  },
  ["ctf-sources"],
  { revalidate: 10, tags: [CTF_SOURCES_TAG] },
);

export async function getChallengeCatalog(): Promise<ChallengeCatalogItem[]> {
  return getCachedChallengeCatalog();
}

export async function getCTFs(): Promise<CTFSourceSummary[]> {
  return getCachedCTFs();
}

export async function importCTF(input: ImportCTFInput): Promise<{
  ctf: CTFSourceSummary;
  importedChallenges: number;
  downloadedFiles: number;
  rootDirectory: string;
}> {
  const payload = await fetchBackend<BackendCTFImportResponse>("/api/v1/ctfs/import", {
    method: "POST",
    body: JSON.stringify({
      name: input.name,
      ctfd_url: input.ctfdUrl,
      auth_mode: input.authMode,
      token: input.token ?? "",
      username: input.username ?? "",
      password: input.password ?? "",
      challenges_root: input.challengesRoot ?? "challenges",
    }),
  });

  revalidateTag(CTF_SOURCES_TAG, "max");
  revalidateTag(CHALLENGE_CATALOG_TAG, "max");

  return {
    ctf: toCTFSource(payload.ctf),
    importedChallenges: payload.imported_challenges,
    downloadedFiles: payload.downloaded_files,
    rootDirectory: payload.root_directory,
  };
}

export async function startChallenge(
  challengeId: string,
): Promise<{ challenge: ChallengeCatalogItem; run: Record<string, unknown> | null }> {
  const payload = await fetchBackend<BackendStartChallengeResponse>("/api/v1/challenges/start", {
    method: "POST",
    body: JSON.stringify({
      challenge_id: challengeId,
      launch_solver: true,
    }),
  });

  revalidateTag(CHALLENGE_CATALOG_TAG, "max");

  return {
    challenge: toCatalogItem(payload.challenge),
    run: payload.run ?? null,
  };
}

export async function killChallenge(
  challengeId: string,
): Promise<{ challenge: ChallengeCatalogItem; cancelledCount: number; containersRemoved: number }> {
  const payload = await fetchBackend<BackendKillChallengeResponse>(
    `/api/v1/challenges/${encodeURIComponent(challengeId)}/kill`,
    {
      method: "POST",
    },
  );

  revalidateTag(CHALLENGE_CATALOG_TAG, "max");

  return {
    challenge: toCatalogItem(payload.challenge),
    cancelledCount: payload.termination?.cancelled_count ?? 0,
    containersRemoved: payload.termination?.containers_removed ?? 0,
  };
}

export async function deleteChallengeData(
  challengeId: string,
): Promise<{ challenge: ChallengeCatalogItem; deletedRuns: number; filesRemoved: number }> {
  const payload = await fetchBackend<BackendDeleteChallengeResponse>(
    `/api/v1/challenges/${encodeURIComponent(challengeId)}`,
    {
      method: "DELETE",
    },
  );

  revalidateTag(CHALLENGE_CATALOG_TAG, "max");

  return {
    challenge: toCatalogItem(payload.challenge),
    deletedRuns: payload.deleted_runs ?? 0,
    filesRemoved: payload.files_removed ?? 0,
  };
}

export async function steerChallenge(
  challengeId: string,
  message: string,
  source = "operator",
): Promise<SteeringChallengeResult> {
  const payload = await fetchBackend<BackendSteerChallengeResponse>(
    `/api/v1/challenges/${encodeURIComponent(challengeId)}/steer`,
    {
      method: "POST",
      body: JSON.stringify({
        message,
        source,
      }),
    },
  );

  return {
    runId: payload.run_id,
    challengeId: payload.challenge_id,
    queued: payload.queued,
    source: payload.source,
    createdAt: payload.created_at,
  };
}
