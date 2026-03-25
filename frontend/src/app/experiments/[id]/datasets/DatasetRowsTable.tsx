"use client";

export interface DatasetRow {
  question: string;
  expectedResponse: string;
}

function firstValue(obj: unknown): string {
  if (obj === null || obj === undefined) return "";
  if (typeof obj !== "object") return String(obj);
  const vals = Object.values(obj as Record<string, unknown>);
  return vals.length > 0 ? String(vals[0] ?? "") : "";
}

export function toTableRows(apiRows: Record<string, unknown>[]): DatasetRow[] {
  return apiRows.map((r) => {
    const inputs = (r["inputs"] as Record<string, unknown>) ?? {};
    const expectations = (r["expectations"] as Record<string, unknown>) ?? {};
    return {
      question: String(inputs["question"] ?? firstValue(inputs)),
      // canonical key is expected_response; fall back to first value for legacy rows
      expectedResponse: String(
        expectations["expected_response"] ?? firstValue(expectations),
      ),
    };
  });
}

export function toApiRows(rows: DatasetRow[]): Record<string, unknown>[] {
  return rows.map((r) => ({
    inputs: { question: r.question },
    expectations: { expected_response: r.expectedResponse },
  }));
}

interface Props {
  rows: DatasetRow[];
  onChange: (rows: DatasetRow[]) => void;
  readOnly: boolean;
}

export function DatasetRowsTable({ rows, onChange, readOnly }: Props) {
  function updateRow(index: number, field: keyof DatasetRow, value: string) {
    const next = rows.map((r, i) => (i === index ? { ...r, [field]: value } : r));
    onChange(next);
  }

  function deleteRow(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }

  function addRow() {
    onChange([...rows, { question: "", expectedResponse: "" }]);
  }

  if (rows.length === 0) {
    return (
      <div className="text-sm text-gray-500 py-4">
        {readOnly ? (
          "No rows."
        ) : (
          <div className="flex flex-col items-start gap-3">
            <span>No rows yet.</span>
            <button
              type="button"
              onClick={addRow}
              className="border border-gray-300 text-gray-700 px-4 py-1.5 rounded text-sm hover:bg-gray-50"
            >
              + Add row
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b border-gray-200 text-left text-gray-600">
              <th className="py-2 pr-3 w-10">#</th>
              <th className="py-2 pr-3 w-1/2">Question</th>
              <th className="py-2 pr-3">Expected Response</th>
              {!readOnly && <th className="py-2 w-8" />}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-gray-100 align-top">
                <td className="py-2 pr-3 text-gray-400 text-xs pt-3">{i + 1}</td>
                <td className="py-2 pr-3">
                  {readOnly ? (
                    <span className="block whitespace-pre-wrap">{row.question}</span>
                  ) : (
                    <input
                      type="text"
                      value={row.question}
                      onChange={(e) => updateRow(i, "question", e.target.value)}
                      className="w-full border border-gray-200 rounded px-2 py-1 text-sm focus:outline-none focus:border-blue-400"
                    />
                  )}
                </td>
                <td className="py-2 pr-3">
                  {readOnly ? (
                    <span className="block whitespace-pre-wrap">{row.expectedResponse}</span>
                  ) : (
                    <textarea
                      value={row.expectedResponse}
                      onChange={(e) =>
                        updateRow(i, "expectedResponse", e.target.value)
                      }
                      rows={3}
                      className="w-full border border-gray-200 rounded px-2 py-1 text-sm focus:outline-none focus:border-blue-400 resize-y"
                    />
                  )}
                </td>
                {!readOnly && (
                  <td className="py-2 pt-3">
                    <button
                      type="button"
                      onClick={() => deleteRow(i)}
                      className="text-red-400 hover:text-red-600 text-lg leading-none"
                      aria-label="Delete row"
                    >
                      &times;
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!readOnly && (
        <button
          type="button"
          onClick={addRow}
          className="mt-3 border border-gray-300 text-gray-700 px-4 py-1.5 rounded text-sm hover:bg-gray-50"
        >
          + Add row
        </button>
      )}
    </div>
  );
}
