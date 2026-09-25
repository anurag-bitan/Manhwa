import { auth } from "../lib/firebaseClient";
import { supabase } from "../lib/supabaseClient";

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

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
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
  });
};

export const generateAudioStory = async ({
  file,
  mangaName = "",
  genre = "",
  season = "",
  chapterNumber = "",
  seriesContext = "",
  pendingJobId = "",
}) => {
  if (pendingJobId) {
    const resumed = await authenticatedFetch(
      `/jobs/${encodeURIComponent(pendingJobId)}/start`,
      { method: "POST" },
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

  let started;
  try {
    started = await authenticatedFetch(
      `/jobs/${encodeURIComponent(upload.job_id)}/start`,
      { method: "POST" },
    );
  } catch (error) {
    if (error instanceof ApiError) error.pendingJobId = upload.job_id;
    throw error;
  }
  return { task_id: started.job_id };
};

export const checkTaskStatus = async (taskId) => {
  const encodedTaskId = encodeURIComponent(taskId);
  const job = await authenticatedFetch(`/jobs/${encodedTaskId}`);
  const status = job.status;

  if (status === "TTS_COMPLETED") {
    const assets = await authenticatedFetch(`/jobs/${encodedTaskId}/assets`);
    return {
      state: "SUCCESS",
      progress: 100,
      result: assets,
    };
  }

  if (status === "FAILED") {
    return {
      state: "FAILURE",
      progress: 0,
      error: job.state_json?.error || "Job failed",
    };
  }

  const progressMap = {
    UPLOAD_PENDING: 2,
    QUEUED: 5,
    PROCESSING: 8,
    UPLOADED: 5,
    EXTRACTED: 15,
    PANELS_DETECTED: 30,
    OCR_COMPLETED: 50,
    CHAPTER_DETECTED: 60,
    SCENE_BUILDING: 70,
    SCRIPT_GENERATING: 80,
  };

  return {
    state: "PROCESSING",
    progress: progressMap[status] || 5,
    result: null,
  };
};
