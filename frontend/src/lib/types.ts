export type TraceStatus =
  | "running"
  | "solved"
  | "gave_up"
  | "cancelled"
  | "error"
  | "unknown";

export type TraceEvent = {
  ts: number;
  type: string;
  step?: number;
  tool?: string;
  args?: string;
  result?: string;
  text?: string;
  status?: string;
  flag?: string | null;
  challenge?: string;
  model?: string;
  error?: string;
  input_tokens?: number;
  output_tokens?: number;
  cache_read_tokens?: number;
  cost_usd?: number;
  confirmed?: boolean;
  [key: string]: unknown;
};

export type TraceSummary = {
  id: string;
  fileName: string;
  challengeId: string;
  challengeName: string;
  modelName: string;
  status: TraceStatus;
  eventCount: number;
  toolCalls: number;
  modelResponses: number;
  lastStep: number;
  preview: string;
  startedAt: string | null;
  updatedAt: string | null;
  inputTokens: number;
  outputTokens: number;
  cacheReadTokens: number;
  costUsd: number;
  flag: string | null;
};

export type ChallengeItem = {
  id: string;
  name: string;
  traceCount: number;
  startedAt: string | null;
  updatedAt: string | null;
  traces: TraceSummary[];
};

export type ChallengeCatalogItem = {
  id: string;
  ctfId: number;
  ctfName: string;
  name: string;
  path: string;
  category: string;
  value: number;
  description: string;
  connectionInfo: string;
  hasDistfiles: boolean;
  distfileCount: number;
  startedAt: string | null;
  updatedAt: string | null;
};

export type CTFSourceSummary = {
  id: number;
  name: string;
  slug: string;
  baseUrl: string;
  authMode: string;
  challengesRoot: string;
  challengeCount: number;
  lastImportAt: string | null;
  lastImportStatus: string;
  lastImportError: string;
  createdAt: string;
  updatedAt: string;
};

export type ImportCTFInput = {
  name: string;
  ctfdUrl: string;
  authMode: "token" | "credentials";
  token?: string;
  username?: string;
  password?: string;
  challengesRoot?: string;
};

export type TraceDetail = {
  summary: TraceSummary;
  events: TraceEvent[];
  terminalOutput: string;
};

export type TraceListResponse = {
  traces: TraceSummary[];
  available: boolean;
  generatedAt: string;
  logsDirectory: string;
};

export type SteeringChallengeResult = {
  runId: string;
  challengeId: string;
  queued: string;
  source: string;
  createdAt: string;
};
