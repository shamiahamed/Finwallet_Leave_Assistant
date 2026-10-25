import { useRef, useState } from "react";
import {
  deleteDataset,
  listDatasets,
  previewDataset,
  uploadDataset,
} from "../services/datasetService";

function DatasetPanel({ selectedDatasetId, onSelectDataset }) {
  const [open, setOpen] = useState(false);
  const [datasets, setDatasets] = useState([]);
  const [defaultId, setDefaultId] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const fileRef = useRef(null);

  async function refreshList() {
    try {
      const data = await listDatasets();
      setDatasets(data.datasets || []);
      setDefaultId(data.default_dataset_id || null);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  }

  function toggleOpen() {
    const next = !open;
    setOpen(next);
    if (next) refreshList();
  }

  async function handleUpload(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const result = await uploadDataset(file);
      setPreview(result.preview);
      await refreshList();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function handlePreview(datasetId) {
    setError(null);
    try {
      setPreview(await previewDataset(datasetId));
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDelete(datasetId) {
    setError(null);
    try {
      await deleteDataset(datasetId);
      if (selectedDatasetId === datasetId) onSelectDataset(null);
      setPreview(null);
      await refreshList();
    } catch (err) {
      setError(err.message);
    }
  }

  function select(datasetId) {
    onSelectDataset(datasetId === defaultId ? null : datasetId);
  }

  const activeLabel =
    datasets.find(
      (d) => d.dataset_id === (selectedDatasetId || defaultId)
    )?.name || "Default workbook";

  return (
    <div className="dataset-panel">
      <button
        type="button"
        className="dataset-toggle"
        onClick={toggleOpen}
        title="Manage datasets"
      >
        <span aria-hidden="true">🗂</span> {activeLabel}
      </button>

      {open && (
        <div className="dataset-dropdown">
          <div className="dataset-dropdown-head">
            <strong>Datasets</strong>
            <button
              type="button"
              className="action-btn"
              onClick={() => setOpen(false)}
            >
              Close
            </button>
          </div>

          <label className="dataset-upload">
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.csv"
              onChange={handleUpload}
              disabled={busy}
            />
            {busy ? "Uploading…" : "Upload .xlsx or .csv"}
          </label>

          {error && <div className="dataset-error">{error}</div>}

          <ul className="dataset-list">
            {datasets.map((d) => (
              <li key={d.dataset_id} className="dataset-item">
                <label className="dataset-name">
                  <input
                    type="radio"
                    name="dataset"
                    checked={
                      (selectedDatasetId || defaultId) === d.dataset_id
                    }
                    onChange={() => select(d.dataset_id)}
                  />
                  <span>
                    {d.name}
                    <span className="dataset-meta">
                      {" "}
                      · {d.source} · {d.validation_status}
                    </span>
                  </span>
                </label>
                <div className="dataset-item-actions">
                  <button
                    type="button"
                    className="action-btn"
                    onClick={() => handlePreview(d.dataset_id)}
                  >
                    Preview
                  </button>
                  {d.source !== "default" && (
                    <button
                      type="button"
                      className="action-btn"
                      onClick={() => handleDelete(d.dataset_id)}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>

          {preview && (
            <div className="dataset-preview">
              <div className="dataset-preview-head">
                Preview · {preview.row_count} rows × {preview.column_count} cols
              </div>
              {preview.warnings?.length > 0 && (
                <ul className="dataset-warnings">
                  {preview.warnings.map((w, i) => (
                    <li key={i}>{w}</li>
                  ))}
                </ul>
              )}
              <div className="dataset-columns">
                {preview.columns.join(", ")}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default DatasetPanel;
