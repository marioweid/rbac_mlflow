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

export interface DatasetSummary {
  id: string; // MLflow dataset_id
  name: string;
  experiment_id: string;
  description: string;
  row_count: number;
  updated_at: string;
}

export interface DatasetDetail {
  id: string; // MLflow dataset_id
  name: string;
  experiment_id: string;
  description: string;
  rows: Record<string, unknown>[];
}

export interface DatasetResponse {
  id: string; // MLflow dataset_id
  name: string;
  experiment_id: string;
  row_count: number;
}

export interface StartRunRequest {
  dataset_id: string; // MLflow dataset_id
  run_name: string | null;
}

export interface StartRunResponse {
  run_id: string;
  experiment_id: string;
  run_name: string;
  status: string;
}
