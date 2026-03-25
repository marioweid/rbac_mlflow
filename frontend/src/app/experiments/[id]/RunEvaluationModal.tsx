"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useSession } from "next-auth/react";

import { clientApiFetch } from "@/lib/client-api";
import type { DatasetSummary, StartRunResponse } from "@/lib/types";

interface Props {
  experimentId: string;
  onClose: () => void;
}

export function RunEvaluationModal({ experimentId, onClose }: Props) {
  const router = useRouter();
  const { data: session } = useSession();

  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>("");
  const [runName, setRunName] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchDatasets() {
      setLoading(true);
      try {
        const res = await clientApiFetch(
          `/experiments/${experimentId}/datasets`,
          session?.accessToken,
        );
        if (!res.ok) {
          setError("Failed to load datasets.");
          return;
        }
        setDatasets((await res.json()) as DatasetSummary[]);
      } catch {
        setError("Failed to load datasets.");
      } finally {
        setLoading(false);
      }
    }
    void fetchDatasets();
  }, [session?.accessToken, experimentId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedDatasetId) return;

    setSubmitting(true);
    setError(null);
    try {
      const res = await clientApiFetch(
        `/experiments/${experimentId}/runs`,
        session?.accessToken,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            dataset_id: selectedDatasetId,
            run_name: runName || null,
          }),
        },
      );
      if (!res.ok) {
        const body = (await res.json()) as { detail?: string };
        setError(body.detail ?? `Error ${res.status}`);
        return;
      }
      const result = (await res.json()) as StartRunResponse;
      router.push(`/experiments/${experimentId}/runs/${result.run_id}`);
    } catch {
      setError("Unexpected error. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold">Run Evaluation</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none"
          >
            &times;
          </button>
        </div>

        {loading ? (
          <p className="text-sm text-gray-500 py-4 text-center">
            Loading datasets&hellip;
          </p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Dataset
              </label>
              {datasets.length === 0 ? (
                <p className="text-sm text-gray-500">
                  No datasets available for this experiment.
                </p>
              ) : (
                <select
                  value={selectedDatasetId}
                  onChange={(e) => setSelectedDatasetId(e.target.value)}
                  required
                  className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
                >
                  <option value="">Select a dataset&hellip;</option>
                  {datasets.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name} ({d.row_count} rows)
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Run name{" "}
                <span className="font-normal text-gray-400">(optional)</span>
              </label>
              <input
                type="text"
                value={runName}
                onChange={(e) => setRunName(e.target.value)}
                placeholder="Auto-generated if left blank"
                className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
              />
            </div>

            {error !== null && (
              <p className="text-sm text-red-600">{error}</p>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={submitting || !selectedDatasetId}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                {submitting ? "Starting\u2026" : "Start evaluation"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
