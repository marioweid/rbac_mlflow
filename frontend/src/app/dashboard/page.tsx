import Link from "next/link";

import { apiFetch } from "@/lib/api";
import { formatTimestamp, statusColor } from "@/lib/format";
import type { ExperimentSummary } from "@/lib/types";

async function getExperiments(): Promise<ExperimentSummary[]> {
  const res = await apiFetch("/experiments");
  if (!res.ok) return [];
  return (await res.json()) as ExperimentSummary[];
}

export default async function DashboardPage() {
  const experiments = await getExperiments();

  return (
    <main className="max-w-6xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Experiments</h1>

      {experiments.length === 0 ? (
        <p className="text-gray-500">
          No experiments found. You may not be a member of any team, or no
          experiments have been linked yet.
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {experiments.map((exp) => (
            <Link
              key={exp.experiment_id}
              href={`/experiments/${exp.experiment_id}`}
              className="block border border-gray-200 rounded-lg p-4 hover:border-blue-400 hover:shadow-sm transition-colors"
            >
              <h2 className="font-semibold text-lg truncate">{exp.name}</h2>
              <span className="inline-block text-xs bg-gray-100 text-gray-600 rounded px-2 py-0.5 mt-1">
                {exp.team_name}
              </span>

              <div className="mt-3 text-sm text-gray-600 space-y-1">
                <div className="flex justify-between">
                  <span>Latest run</span>
                  <span className={statusColor(exp.latest_run_status)}>
                    {exp.latest_run_status ?? "No runs"}
                  </span>
                </div>

                {exp.key_metric_name !== null &&
                  exp.key_metric_value !== null && (
                    <div className="flex justify-between">
                      <span>{exp.key_metric_name}</span>
                      <span className="font-mono">
                        {exp.key_metric_value.toFixed(4)}
                      </span>
                    </div>
                  )}

                {exp.last_update_time !== null && (
                  <div className="text-xs text-gray-400 mt-2">
                    Updated {formatTimestamp(exp.last_update_time)}
                  </div>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
