import { auth } from "../lib/firebaseClient";
import { supabase } from "../lib/supabaseClient";
import { renderPdfPagesToJpegs } from "../utils/renderPdfPages";

const API_URL = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, status = 0, details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

async function parseResponse(response) {
  const text = await response.text();
  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function errorMessage(payload, status) {
  if (typeof payload === "string" && payload.trim()) return payload;
  if (typeof payload?.detail === "string") return payload.detail;
  if (typeof payload?.message === "string") return payload.message;
  return `Backend request failed (${status})`;
}

async function getIdToken() {
  const currentUser = auth.currentUser;
  if (!currentUser) {
    throw new ApiError("Your session expired. Please sign in again.", 401);
  }
  try {
    return await currentUser.getIdToken();
  } catch {
    throw new ApiError("Your session expired. Please sign in again.", 401);
  }
}

async function authenticatedFetch(path, options = {}) {
  if (!API_URL) {
    throw new ApiError("VITE_API_BASE_URL is not configured.");
  }

  const headers = new Headers(options.headers);
  headers.set("Authorization", `Bearer ${await getIdToken()}`);

  const { signal, ...rest } = options;
  const response = await fetch(`${API_URL}${path}`, {
    ...rest,
    headers,
    signal,
  });
  const payload = await parseResponse(response);

  if (!response.ok) {
    throw new ApiError(errorMessage(payload, response.status), response.status, payload);
  }

  return payload;
}

export const previewManhwaContext = async ({
  manhwaName,
  season = "",
  chapterNumber = "",
  genre = "",
  signal,
}) => {
  if (!manhwaName?.trim()) {
    return { context: "", grounded: false, word_count: 0 };
  }

  return authenticatedFetch("/context/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      manhwa_name: manhwaName.trim(),
      season: season.trim(),
      chapter_number: chapterNumber.trim(),
      genre: genre.trim(),
    }),
    signal,
  });
};

async function uploadClientPages(jobId, file, onProgress) {
  const blobs = await renderPdfPagesToJpegs(file, {
    onProgress: (current, total) => onProgress?.(`Rendering page ${current}/${total}`, current, total),
  });
  if (!blobs.length) return { client_pages: false, page_count: 0 };

  onProgress?.(`Uploading ${blobs.length} pages`, 0, blobs.length);
  const signed = await authenticatedFetch(
    `/jobs/${encodeURIComponent(jobId)}/page-upload-urls`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_count: blobs.length }),
    },
  );

  for (const page of signed.pages || []) {
    const blob = blobs[page.index];
    if (!blob) continue;
    const result = await supabase.storage
      .from("pages")
      .uploadToSignedUrl(page.path, page.token, blob, {
        contentType: "image/jpeg",
        upsert: false,
      });
    if (result.error) {
      throw new ApiError(result.error.message || "A page image could not be uploaded.", 502);
    }
    onProgress?.(`Uploading page ${page.index + 1}/${blobs.length}`, page.index + 1, blobs.length);
  }

  return { client_pages: true, page_count: blobs.length };
}

export const generateAudioStory = async ({
  file,
  mangaName = "",
  genre = "",
  season = "",
  chapterNumber = "",
  seriesContext = "",
  pendingJobId = "",
  onProgress,
}) => {
  if (pendingJobId) {
    const resumed = await authenticatedFetch(
      `/jobs/${encodeURIComponent(pendingJobId)}/start`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      },
    );
    return { task_id: resumed.job_id };
  }

  const contentType = file.type || "application/pdf";
  const upload = await authenticatedFetch("/jobs/upload-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: file.name,
      size_bytes: file.size,
      content_type: contentType,
      manhwa_name: mangaName,
      genre,
      season,
      chapter_number: chapterNumber,
      series_context: seriesContext,
    }),
  });

  let storageResult;
  try {
    storageResult = await supabase.storage
      .from("pdfs")
      .uploadToSignedUrl(upload.path, upload.token, file, {
        contentType,
        upsert: false,
      });
  } catch {
    throw new ApiError("The PDF upload could not be completed. Please retry.", 502);
  }
  if (storageResult.error) {
    throw new ApiError(
      storageResult.error.message || "The PDF upload could not be completed.",
      502,
    );
  }

  let clientPages = { client_pages: false, page_count: 0 };
  try {
    onProgress?.("Rendering pages in the browser", 0, 1);
    clientPages = await uploadClientPages(upload.job_id, file, onProgress);
  } catch (error) {
    console.warn("Browser page extract failed; server will render pages.", error);
  }

  let started;
  try {
    started = await authenticatedFetch(
      `/jobs/${encodeURIComponent(upload.job_id)}/start`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(clientPages),
      },
    );
  } catch (error) {
    if (error instanceof ApiError) error.pendingJobId = upload.job_id;
    throw error;
  }
  return { task_id: started.job_id };
};

const STAGE_RANGE = {
  UPLOAD_PENDING: [2, 5],
  QUEUED: [5, 8],
  PROCESSING: [8, 12],
  EXTRACTED: [12, 22],
  PANELS_DETECTED: [22, 55],
  OCR_COMPLETED: [55, 62],
  CHAPTER_DETECTED: [58, 62],
  SCENE_BUILDING: [62, 70],
  SCRIPT_GENERATING: [70, 92],
};

function interpolateProgress(status, progress) {
  const [start, end] = STAGE_RANGE[status] || [5, 10];
  const current = Number(progress?.current);
  const total = Number(progress?.total);
  if (current > 0 && total > 0) {
    return Math.round(start + ((end - start) * Math.min(1, current / total)));
  }
  return start;
}

export const checkTaskStatus = async (taskId) => {
  const encodedTaskId = encodeURIComponent(taskId);
  const job = await authenticatedFetch(`/jobs/${encodedTaskId}`);
  const status = job.status;
  const progressMeta = job.state_json?.progress || {};

  if (status === "TTS_COMPLETED") {
    const assets = await authenticatedFetch(`/jobs/${encodedTaskId}/assets`);
    return {
      state: "SUCCESS",
      progress: 100,
      detail: "Done",
      result: assets,
    };
  }

  if (status === "FAILED") {
    return {
      state: "FAILURE",
      progress: 0,
      detail: "",
      error: job.state_json?.error || "Job failed",
    };
  }

  return {
    state: "PROCESSING",
    progress: interpolateProgress(status, progressMeta),
    detail: progressMeta.detail || status.replaceAll("_", " ").toLowerCase(),
    result: null,
  };
};
