"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { useSession } from "next-auth/react";

import { clientApiFetch } from "@/lib/client-api";
import type { DatasetResponse } from "@/lib/types";

import {
  DatasetRowsTable,
  toApiRows,
} from "../DatasetRowsTable";
import type { DatasetRow } from "../DatasetRowsTable";

export default function NewDatasetPage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const experimentId = params.id;
  const { data: session } = useSession();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [rows, setRows] = useState<DatasetRow[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await clientApiFetch(
        `/experiments/${experimentId}/datasets`,
        session?.accessToken,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, description, rows: toApiRows(rows) }),
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
      const created = (await res.json()) as DatasetResponse;
      router.push(`/experiments/${experimentId}/datasets/${created.id}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="max-w-4xl mx-auto p-6">
      <Link
        href={`/experiments/${experimentId}`}
        className="text-sm text-blue-600 hover:underline mb-4 block"
      >
        &larr; Back to experiment
      </Link>

      <h1 className="text-2xl font-bold mb-6">New dataset</h1>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium mb-1">Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="w-full border border-gray-200 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-1">
            Description{" "}
            <span className="text-gray-400 font-normal">(optional)</span>
          </label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full border border-gray-200 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
          />
        </div>

        <div>
          <label className="block text-sm font-medium mb-2">Rows</label>
          <DatasetRowsTable rows={rows} onChange={setRows} readOnly={false} />
        </div>

        {error !== null && <p className="text-red-600 text-sm">{error}</p>}

        <button
          type="submit"
          disabled={submitting}
          className="bg-blue-600 text-white px-6 py-2 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? "Creating\u2026" : "Create dataset"}
        </button>
      </form>
    </main>
  );
}
