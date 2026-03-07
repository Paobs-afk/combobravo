<template>
  <section class="page-grid">
    <article class="panel">
      <h2>Upload New Dataset</h2>
      <p class="hint">
        CSV must include an <code>items</code> column (or <code>basket</code>) with comma-separated meals.
      </p>

      <label class="control">
        Dataset Name
        <input v-model="datasetName" type="text" placeholder="example: cafe_march_sales" />
      </label>

      <label class="control">
        CSV File
        <input type="file" accept=".csv" @change="onFileChange" />
      </label>

      <button class="upload-btn" :disabled="uploading || !selectedFile" @click="submitUpload">
        {{ uploading ? "Uploading..." : "Upload and Train" }}
      </button>

      <p v-if="message" class="success">{{ message }}</p>
      <p v-if="error" class="error">{{ error }}</p>
    </article>

    <article class="panel">
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
          <tr v-for="dataset in datasets" :key="dataset.id">
            <td>{{ dataset.id }}</td>
            <td>{{ dataset.label }}</td>
            <td>{{ dataset.transactions }}</td>
            <td>{{ dataset.unique_items }}</td>
            <td>
              <button class="mini-btn" @click="useDataset(dataset.id)">Use</button>
            </td>
          </tr>
        </tbody>
      </table>
    </article>
  </section>
</template>

<script setup>
import { ref } from "vue";
import { uploadDataset } from "../services/api";

const props = defineProps({
  datasets: { type: Array, default: () => [] },
});

const emit = defineEmits(["uploaded", "refresh-request"]);

const datasetName = ref("");
const selectedFile = ref(null);
const uploading = ref(false);
const message = ref("");
const error = ref("");

const onFileChange = (event) => {
  const file = event.target.files?.[0];
  selectedFile.value = file || null;
};

const submitUpload = async () => {
  if (!selectedFile.value) {
    return;
  }
  uploading.value = true;
  message.value = "";
  error.value = "";
  try {
    const response = await uploadDataset(selectedFile.value, datasetName.value);
    message.value = `Uploaded successfully: ${response.dataset_id} (${response.transactions} transactions).`;
    emit("refresh-request");
    emit("uploaded", response.dataset_id);
  } catch (uploadError) {
    error.value = uploadError.message;
  } finally {
    uploading.value = false;
  }
};

const useDataset = (datasetId) => {
  emit("uploaded", datasetId);
};
</script>

<style scoped>
.page-grid {
  display: grid;
  gap: 12px;
}

.panel {
  border: 1px solid #efc7c2;
  border-radius: 12px;
  background: #fff;
  padding: 14px;
}

.hint {
  margin-top: 0;
  color: #74403a;
}

.control {
  display: grid;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 0.75rem;
  text-transform: uppercase;
  font-weight: 700;
  color: #7a362f;
}

input[type="text"],
input[type="file"] {
  border: 1px solid #f1c8c2;
  border-radius: 10px;
  background: #fff;
  padding: 8px 10px;
}

.upload-btn,
.mini-btn {
  border: 1px solid #f1c8c2;
  border-radius: 10px;
  background: #fff4f2;
  color: #8a1e13;
  padding: 8px 12px;
  font-weight: 700;
  cursor: pointer;
}

.upload-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  border-bottom: 1px solid #f0d7d4;
  padding: 8px;
  text-align: left;
}

th {
  font-size: 0.74rem;
  text-transform: uppercase;
  color: #8f4740;
}

.success {
  color: #1f7d3f;
  font-weight: 700;
}

.error {
  color: #8a1e13;
  font-weight: 700;
}
</style>
