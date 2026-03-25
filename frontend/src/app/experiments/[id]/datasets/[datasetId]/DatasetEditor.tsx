"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { useSession } from "next-auth/react";

import { clientApiFetch } from "@/lib/client-api";
import type { DatasetDetail } from "@/lib/types";

import {
  DatasetRowsTable,
  toApiRows,
  toTableRows,
} from "../DatasetRowsTable";
import type { DatasetRow } from "../DatasetRowsTable";

interface Props {
  dataset: DatasetDetail;
  experimentId: string;
  canWrite: boolean;
}

export function DatasetEditor({ dataset, experimentId, canWrite }: Props) {
  const router = useRouter();
  const { data: session } = useSession();

  const [rows, setRows] = useState<DatasetRow[]>(toTableRows(dataset.rows));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await clientApiFetch(
        `/experiments/${experimentId}/datasets/${dataset.id}`,
        session?.accessToken,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rows: toApiRows(rows) }),
        },
      );
      if (!res.ok) {
        let message = `Error ${res.status}`;
        try {
          const body = (await res.json()) as { detail?: string };
          message = body.detail ?? message;
        } catch {
          // response body was not JSON
        }
        setError(message);
        return;
      }
      router.refresh();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-lg font-semibold">Rows</h2>
        {canWrite && (
          <button
            onClick={handleSave}
            disabled={saving}
            className="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? "Saving\u2026" : "Save"}
          </button>
        )}
      </div>

      {error !== null && <p className="text-red-600 text-sm mb-2">{error}</p>}

      <DatasetRowsTable rows={rows} onChange={setRows} readOnly={!canWrite} />
    </div>
  );
}
