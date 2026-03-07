import { useState } from "react";
import { uploadDataset } from "../services/api";

function UploadPage({ datasets = [], onUploaded, onRefreshRequest }) {
  const [datasetName, setDatasetName] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const onFileChange = (event) => {
    const file = event.target.files?.[0];
    setSelectedFile(file || null);
  };

  const submitUpload = async () => {
    if (!selectedFile) {
      return;
    }

    setUploading(true);
    setMessage("");
    setError("");

    try {
      const response = await uploadDataset(selectedFile, datasetName);
      setMessage(
        `Uploaded successfully: ${response.dataset_id} (${response.transactions} transactions).`
      );
      if (typeof onRefreshRequest === "function") {
        onRefreshRequest();
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

  return (
    <section className="page-grid">
      <section className="split-grid">
        <article className="panel">
          <h2>Upload New Dataset</h2>
          <p className="hint">
            CSV must include an <code>items</code> column (or <code>basket</code>) with
            comma-separated products. At least 90 valid transactions are required.
          </p>

          <label className="control">
            Dataset Name
            <input
              value={datasetName}
              onChange={(event) => setDatasetName(event.target.value)}
              type="text"
              placeholder="example: cafe_march_sales"
            />
          </label>

          <label className="control">
            CSV File
            <input type="file" accept=".csv" onChange={onFileChange} />
          </label>

          <button
            className="upload-btn"
            disabled={uploading || !selectedFile}
            onClick={submitUpload}
            type="button"
          >
            {uploading ? "Uploading..." : "Upload and Train"}
          </button>

          {message ? <p className="success">{message}</p> : null}
          {error ? <p className="error">{error}</p> : null}
        </article>

        <article className="panel">
          <h2>Template CSV Files</h2>
          <p className="hint">
            Two ready-to-upload CSV files are provided in
            <code>backend/data/upload_samples</code>:
          </p>
          <ul className="sample-list">
            <li>
              <code>sample_city_cafe.csv</code>
            </li>
            <li>
              <code>sample_campus_bites.csv</code>
            </li>
          </ul>
          <p className="hint">You can edit these files and upload them directly in this page.</p>
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
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {datasets.map((dataset) => (
              <tr key={dataset.id}>
                <td>{dataset.id}</td>
                <td>{dataset.label}</td>
                <td>{dataset.transactions}</td>
                <td>{dataset.unique_items}</td>
                <td>
                  <button
                    className="mini-btn"
                    onClick={() => useDataset(dataset.id)}
                    type="button"
                  >
                    Use
                  </button>
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
