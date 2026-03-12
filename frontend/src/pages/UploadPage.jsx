import { useMemo, useRef, useState } from "react";
import TabIcon from "../components/TabIcon";
import { deleteDataset, uploadDataset } from "../services/api";

function UploadPage({ datasets = [], onUploaded, onRefreshRequest }) {
  const [assignment, setAssignment] = useState("custom");
  const [uploadMode, setUploadMode] = useState("append");
  const [datasetName, setDatasetName] = useState("");
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [deletingDatasetId, setDeletingDatasetId] = useState("");
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);

  const resolvedDatasetName = useMemo(() => {
    if (assignment === "A") return "A";
    if (assignment === "B") return "B";
    return datasetName.trim() || "uploaded";
  }, [assignment, datasetName]);

  const resolvedUploadMode = useMemo(
    () => (assignment === "custom" ? uploadMode : "replace"),
    [assignment, uploadMode]
  );

  const onFileChange = (event) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) {
      return;
    }
    setSelectedFiles((previous) => {
      const seen = new Set(previous.map((file) => `${file.name}-${file.size}-${file.lastModified}`));
      const next = [...previous];
      for (const file of files) {
        const key = `${file.name}-${file.size}-${file.lastModified}`;
        if (seen.has(key)) {
          continue;
        }
        seen.add(key);
        next.push(file);
      }
      return next;
    });
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const removeSelectedFile = (indexToRemove) => {
    setSelectedFiles((previous) => previous.filter((_, index) => index !== indexToRemove));
  };

  const clearSelectedFiles = () => {
    setSelectedFiles([]);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const submitUpload = async () => {
    if (!selectedFiles.length) {
      return;
    }

    setUploading(true);
    setMessage("");
    setError("");

    try {
      const response = await uploadDataset(selectedFiles, resolvedDatasetName, resolvedUploadMode);
      setMessage(
        `Uploaded as ${response.dataset_id}: mode=${response.upload_mode}, ${response.uploaded_file_count} file(s), ${response.batch_count} batch(es), ${response.new_transactions} new tx, ${response.transactions} total tx, trained up to iteration ${response.trained_iterations}.`
      );
      clearSelectedFiles();
      if (typeof onRefreshRequest === "function") {
        await onRefreshRequest();
      }
      if (typeof onUploaded === "function") {
        onUploaded(response.dataset_id);
      }
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setUploading(false);
    }
  };

  const useDataset = (datasetId) => {
    if (typeof onUploaded === "function") {
      onUploaded(datasetId);
    }
  };

  const removeDataset = async (datasetId, label) => {
    const confirmed = window.confirm(`Delete dataset "${label}" (${datasetId})? This cannot be undone.`);
    if (!confirmed) {
      return;
    }
    setDeletingDatasetId(datasetId);
    setMessage("");
    setError("");
    try {
      await deleteDataset(datasetId);
      setMessage(`Dataset ${datasetId} deleted.`);
      if (typeof onRefreshRequest === "function") {
        await onRefreshRequest();
      }
    } catch (deleteError) {
      setError(deleteError.message);
    } finally {
      setDeletingDatasetId("");
    }
  };

  const canDeleteDataset = (dataset) => {
    const protectedIds = new Set(["A", "B", "C", "D", "E", "F", "all"]);
    return !protectedIds.has(String(dataset.id));
  };

  return (
    <section className="page-grid">
      <article className="panel">
        <div className="tab-header">
          <span className="tab-avatar">
            <TabIcon name="upload" />
          </span>
          <div>
            <h2>CSV Dataset Upload and Assignment</h2>
            <p className="muted">
              Upload a CSV and assign it directly as Dataset A, Dataset B, or a custom dataset ID.
            </p>
          </div>
        </div>
      </article>

      <section className="split-grid">
        <article className="panel">
          <h2>Upload New Dataset</h2>
          <p className="hint">
            CSV must include an <code>items</code> column (or <code>basket</code>) with comma-separated
            products and at least 90 valid rows.
          </p>
          <p className="hint">
            If you upload <strong>2 or more CSV files</strong>, each file becomes one batch
            (file order = Batch 1, Batch 2, Batch 3...). For separate uploads, use <strong>Append</strong> to continue
            batch numbering (next upload becomes next batch).
          </p>

          <label className="control">
            Dataset Assignment
            <select value={assignment} onChange={(event) => setAssignment(event.target.value)}>
              <option value="A">Dataset A slot (overwrite A)</option>
              <option value="B">Dataset B slot (overwrite B)</option>
              <option value="custom">Custom dataset ID</option>
            </select>
          </label>

          {assignment === "custom" ? (
            <>
              <label className="control">
                Custom Dataset Name
                <input
                  value={datasetName}
                  onChange={(event) => setDatasetName(event.target.value)}
                  type="text"
                  placeholder="example: campus_march_week1"
                />
              </label>

              <label className="control">
                Upload Mode
                <select value={uploadMode} onChange={(event) => setUploadMode(event.target.value)}>
                  <option value="replace">Replace dataset (start over)</option>
                  <option value="append">Append as next batch (Recommended)</option>
                </select>
              </label>
            </>
          ) : null}

          <label className="control">
            CSV File(s)
            <input ref={fileInputRef} type="file" accept=".csv" multiple onChange={onFileChange} />
          </label>

          <p className="hint">
            Final dataset key: <strong>{resolvedDatasetName}</strong>
          </p>
          <p className="hint">
            Effective upload mode: <strong>{resolvedUploadMode}</strong>
          </p>
          <p className="hint">
            Selected files: <strong>{selectedFiles.length}</strong>
          </p>
          {selectedFiles.length ? (
            <>
              <div className="card-stack">
                {selectedFiles.map((file, index) => (
                  <article key={`${file.name}-${index}`} className="suggestion-row">
                    <div>
                      <strong>Batch {index + 1}</strong>
                      <p>
                        <code>{file.name}</code> ({(file.size / 1024).toFixed(1)} KB)
                      </p>
                    </div>
                    <button className="mini-btn" onClick={() => removeSelectedFile(index)} type="button">
                      Cancel File
                    </button>
                  </article>
                ))}
              </div>
              <button className="mini-btn" onClick={clearSelectedFiles} type="button">
                Clear All Files
              </button>
            </>
          ) : null}

          <button
            className="upload-btn"
            disabled={uploading || !selectedFiles.length}
            onClick={submitUpload}
            type="button"
          >
            {uploading ? "Uploading..." : "Upload and Train"}
          </button>

          {message ? <p className="success">{message}</p> : null}
          {error ? <p className="error">{error}</p> : null}
        </article>

        <article className="panel">
          <h2>CSV Format Guide</h2>
          <p className="hint">Required columns:</p>
          <ul className="sample-list">
            <li>
              <code>items</code> or <code>basket</code> (required)
            </li>
            <li>
              <code>timestamp</code> (optional)
            </li>
            <li>
              <code>segment</code> and <code>day_type</code> (optional)
            </li>
          </ul>
          <p className="hint">
            Sample files are in <code>backend/data/upload_samples</code>.
          </p>
          <p className="hint">
            Iterations now follow your batch numbers. Append uploads keep increasing the batch count.
          </p>
        </article>
      </section>

      <article className="panel">
        <h2>Available Datasets</h2>
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Label</th>
              <th>Transactions</th>
              <th>Unique Items</th>
              <th>Batches</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {datasets
              .filter((dataset) => dataset.id !== "all")
              .map((dataset) => (
              <tr key={dataset.id}>
                <td>{dataset.id}</td>
                <td>{dataset.label}</td>
                <td>{dataset.transactions}</td>
                <td>{dataset.unique_items}</td>
                <td>{dataset.batch_count ?? "-"}</td>
                <td>
                  <button className="mini-btn" onClick={() => useDataset(dataset.id)} type="button">
                    Use
                  </button>
                  {canDeleteDataset(dataset) ? (
                    <button
                      className="mini-btn"
                      onClick={() => removeDataset(dataset.id, dataset.label)}
                      type="button"
                      disabled={deletingDatasetId === dataset.id}
                      style={{ marginLeft: "6px" }}
                    >
                      {deletingDatasetId === dataset.id ? "Deleting..." : "Delete"}
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </section>
  );
}

export default UploadPage;
