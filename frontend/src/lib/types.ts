export interface ExperimentSummary {
  experiment_id: string;
  name: string;
  lifecycle_stage: string;
  creation_time: number | null;
  last_update_time: number | null;
  team_name: string;
  latest_run_status: string | null;
  latest_run_id: string | null;
  latest_run_start_time: number | null;
  key_metric_name: string | null;
  key_metric_value: number | null;
}

export interface ExperimentDetail {
  experiment_id: string;
  name: string;
  artifact_location: string;
  lifecycle_stage: string;
  creation_time: number | null;
  last_update_time: number | null;
  team_name: string;
}

export interface MetricEntry {
  key: string;
  value: number;
  timestamp: number | null;
  step: number | null;
}

export interface ParamEntry {
  key: string;
  value: string;
}

export interface TagEntry {
  key: string;
  value: string;
}

export interface RunSummary {
  run_id: string;
  run_name: string | null;
  status: string;
  start_time: number | null;
  end_time: number | null;
  metrics: MetricEntry[];
}

export interface RunDetail {
  run_id: string;
  run_name: string | null;
  experiment_id: string;
  status: string;
  start_time: number | null;
  end_time: number | null;
  artifact_uri: string | null;
  lifecycle_stage: string | null;
  metrics: MetricEntry[];
  params: ParamEntry[];
  tags: TagEntry[];
}

export interface RunListResponse {
  runs: RunSummary[];
  next_page_token: string | null;
}

export interface DatasetVersionInfo {
  version: number;
  row_count: number;
  created_by: string;
  created_at: string;
}

export interface DatasetSummary {
  id: string;
  name: string;
  team_name: string;
  description: string;
  latest_version: number;
  row_count: number;
  updated_at: string;
  is_active: boolean;
}

export interface DatasetDetail {
  id: string;
  name: string;
  team_name: string;
  description: string;
  versions: DatasetVersionInfo[];
  rows: Record<string, unknown>[];
}

export interface DatasetResponse {
  id: string;
  name: string;
  version: number;
  row_count: number;
}

export interface StartRunRequest {
  dataset_id: string;
  dataset_version: number | null;
  run_name: string | null;
}

export interface StartRunResponse {
  run_id: string;
  experiment_id: string;
  run_name: string;
  status: string;
}
