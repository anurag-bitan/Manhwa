import React, { useState, useRef, useEffect, useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../context/useAuth";
import { showToast } from "../utils/toast";
import {
  Upload,
  Download,
  Trash,
  CheckCircle,
  AlertCircle,
  Loader2,
  FileText,
  Settings,
  Lock,
  Video,
  Film,
  Zap,
  Cpu,
  Maximize,
  Minimize,
  Info,
} from "lucide-react";

import { ApiError, generateAudioStory, checkTaskStatus, previewManhwaContext } from '../api/api';
import { generateVideoFromScenes } from '../utils/videoMaker';
import PanelPreviewGrid from "../components/PanelPreviewGrid";
import { buildPanelCards } from "../utils/panelCards";

const configuredMaxPdfMb = Number(import.meta.env.VITE_MAX_PDF_MB || 50);
const MAX_PDF_MB = Number.isFinite(configuredMaxPdfMb) && configuredMaxPdfMb > 0
  ? configuredMaxPdfMb
  : 50;
const MAX_PDF_BYTES = MAX_PDF_MB * 1024 * 1024;

const UploadPage = () => {
  const [file, setFile] = useState(null);
  const [mangaName, setMangaName] = useState("");
  const [season, setSeason] = useState("");
  const [chapterNumber, setChapterNumber] = useState("");
  const [genre, setGenre] = useState("");
  const [seriesContext, setSeriesContext] = useState("");
  const [contextLoading, setContextLoading] = useState(false);
  const [contextGrounded, setContextGrounded] = useState(false);
  const [mode, setMode] = useState("images");
  const [videoUrl, setVideoUrl] = useState(null);
  const [videoBlob, setVideoBlob] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressDetail, setProgressDetail] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState(null);
  const [storyData, setStoryData] = useState(null);
  const [panelImages, setPanelImages] = useState([]);
  const [isGeneratingVideo, setIsGeneratingVideo] = useState(false);
  const [videoProgress, setVideoProgress] = useState(0);
  const [videoLogs, setVideoLogs] = useState([]);
  const [isDownloading, setIsDownloading] = useState(false);
  const [pendingJobId, setPendingJobId] = useState("");

  const fileInputRef = useRef(null);
  const videoContainerRef = useRef(null);
  const videoRef = useRef(null);
  const contextDebounceRef = useRef(null);
  const contextAbortRef = useRef(null);

  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();

  const panelCards = useMemo(
    () => buildPanelCards(storyData, panelImages),
    [storyData, panelImages],
  );
  const chapterStory = (storyData?.story_summary || "").trim();
  const summaryReady = Boolean(seriesContext.trim());
  const showSummaryWaitTooltip = Boolean(
    file && !isProcessing && !storyData && !isGeneratingVideo && !summaryReady,
  );

  // Restore session data on mount
  useEffect(() => {
    const savedData = sessionStorage.getItem("pendingStory");
    const savedFileName = sessionStorage.getItem("pendingFileName");
    const savedVideoUrl = sessionStorage.getItem("pendingVideoUrl");
    const savedIsGeneratingVideo = sessionStorage.getItem("isGeneratingVideo");
    const savedVideoProgress = sessionStorage.getItem("videoProgress");
    const savedVideoLogs = sessionStorage.getItem("videoLogs");

    if (savedData && savedFileName) {
      try {
        const parsed = JSON.parse(savedData);
        setStoryData(parsed);
        setPanelImages(parsed.image_urls || []);
        setMangaName(savedFileName);

        const dummyFile = { name: savedFileName, size: 0, type: "application/pdf" };
        setFile(dummyFile);

        // Restore video if available
        if (savedVideoUrl) {
          setVideoUrl(savedVideoUrl);
        }

        // Restore video generation state if it was in progress
        if (savedIsGeneratingVideo === "true") {
          setIsGeneratingVideo(true);
          setVideoProgress(parseInt(savedVideoProgress || "0"));
          if (savedVideoLogs) {
            setVideoLogs(JSON.parse(savedVideoLogs));
          }
          // Resume video generation
          resumeVideoGeneration(parsed);
        }

        console.log(" Session Restored", savedVideoUrl ? "(with video)" : "");
      } catch (e) {
        console.error("Failed to restore session", e);
      }
    }
  }, []);

  useEffect(() => {
    if (contextDebounceRef.current) {
      clearTimeout(contextDebounceRef.current);
    }
    if (contextAbortRef.current) {
      contextAbortRef.current.abort();
      contextAbortRef.current = null;
    }

    const trimmedName = mangaName.trim();
    if (!trimmedName || trimmedName.length < 2) {
      setSeriesContext("");
      setContextGrounded(false);
      setContextLoading(false);
      return;
    }

    setContextLoading(true);
    const controller = new AbortController();
    contextAbortRef.current = controller;
    contextDebounceRef.current = setTimeout(async () => {
      try {
        const preview = await previewManhwaContext({
          manhwaName: trimmedName,
          season,
          chapterNumber,
          genre,
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setSeriesContext(preview.context || "");
        setContextGrounded(Boolean(preview.grounded));
      } catch (err) {
        if (err?.name === "AbortError" || controller.signal.aborted) return;
        if (err instanceof ApiError && err.status === 401) {
          showToast.error(
            "The API rejected your login token. Sign in again, or check Firebase service account config on the backend.",
          );
          await logout().catch(() => {});
          navigate("/login", {
            replace: true,
            state: { from: { pathname: location.pathname } },
          });
          return;
        }
      } finally {
        if (!controller.signal.aborted) {
          setContextLoading(false);
        }
      }
    }, 600);

    return () => {
      if (contextDebounceRef.current) {
        clearTimeout(contextDebounceRef.current);
      }
      controller.abort();
    };
  }, [mangaName, season, chapterNumber, genre, logout, navigate, location.pathname]);

  // Save video generation state to session storage
  useEffect(() => {
    if (isGeneratingVideo) {
      sessionStorage.setItem("isGeneratingVideo", "true");
      sessionStorage.setItem("videoProgress", videoProgress.toString());
      sessionStorage.setItem("videoLogs", JSON.stringify(videoLogs));
    } else {
      sessionStorage.removeItem("isGeneratingVideo");
      sessionStorage.removeItem("videoProgress");
      sessionStorage.removeItem("videoLogs");
    }
  }, [isGeneratingVideo, videoProgress, videoLogs]);

  // Save video URL to session storage whenever it changes
  useEffect(() => {
    if (videoUrl) {
      sessionStorage.setItem("pendingVideoUrl", videoUrl);
    }
  }, [videoUrl]);

  // Resume video generation if it was interrupted
  const resumeVideoGeneration = async (data) => {
    try {
      setVideoLogs(prev => [...prev, "Resuming video generation..."]);

      setVideoLogs(prev => [...prev, "Video engine ready, continuing generation..."]);

      const result = await generateVideoFromScenes({
        imageUrls: data.image_urls,
        audioUrl: data.audio_url,
        scenes: data.final_video_segments,
        onProgress: (p) => {
          const safeProgress = Math.min(Math.floor(p), 100);
          setVideoProgress(safeProgress);
        },
        onLog: (msg) => setVideoLogs(prev => [...prev, msg]),
      });

      setVideoUrl(result.videoUrl);
      setVideoBlob(result.blob);
      setVideoProgress(100);

      setTimeout(() => {
        setIsGeneratingVideo(false);
      }, 500);

      showToast.success("Video generated successfully!");

    } catch (err) {
      console.error("Resume video generation error:", err);
      setError(err.message || "Video generation failed");
      setIsGeneratingVideo(false);
      setVideoProgress(0);
      showToast.error(err.message || "Video generation failed");
    }
  };

  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = `
      @keyframes shimmer {
        0% { transform: translateX(-100%); }
        100% { transform: translateX(100%); }
      }
      .animate-shimmer {
        animation: shimmer 2s infinite;
      }
    `;
    document.head.appendChild(style);
    return () => document.head.removeChild(style);
  }, []);

  const validateFile = (fileToValidate) => {
    if (!fileToValidate) return false;
    const hasPdfName = fileToValidate.name?.toLowerCase().endsWith(".pdf");
    const hasPdfType = !fileToValidate.type || fileToValidate.type.includes("pdf");
    if (!hasPdfName || !hasPdfType) {
      setError("Please upload a PDF file");
      showToast.error("Please upload a PDF file");
      return false;
    }
    if (fileToValidate.size > MAX_PDF_BYTES) {
      setError(`PDF must be ${MAX_PDF_MB} MB or smaller`);
      showToast.error(`PDF file size must be ${MAX_PDF_MB} MB or smaller`);
      return false;
    }
    setError(null);
    return true;
  };

  const handleFile = (selectedFile) => {
    if (validateFile(selectedFile)) {
      setFile(selectedFile);
      setVideoUrl(null);
      setVideoBlob(null);
      if (!mangaName.trim()) {
        setMangaName(selectedFile.name.replace(/\.pdf$/i, ""));
      }
      setPanelImages([]);
      setStoryData(null);
      setProgress(0);
      setError(null);
      setVideoLogs([]);
      setPendingJobId("");

      sessionStorage.removeItem("pendingStory");
      sessionStorage.removeItem("pendingFileName");
      sessionStorage.removeItem("pendingVideoUrl");
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    handleFile(e.dataTransfer.files[0]);
  };

  const removeFile = () => {
    setFile(null);
    setMangaName("");
    setSeason("");
    setChapterNumber("");
    setGenre("");
    setSeriesContext("");
    setContextGrounded(false);
    setVideoUrl(null);
    setVideoBlob(null);
    setError(null);
    setProgress(0);
    setPanelImages([]);
    setStoryData(null);
    setVideoLogs([]);
    setPendingJobId("");

    sessionStorage.removeItem("pendingStory");
    sessionStorage.removeItem("pendingFileName");
    sessionStorage.removeItem("pendingVideoUrl");

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleGenerateStory = async () => {
    if (!file || file.size === 0) {
      setError("Please upload a PDF first");
      showToast.error("Please upload a PDF first");
      return;
    }

    setIsProcessing(true);
    setProgress(0);
    setProgressDetail("Starting upload");
    setError(null);
    setPanelImages([]);
    setStoryData(null);
    setVideoUrl(null);
    setVideoBlob(null);
    sessionStorage.removeItem("pendingVideoUrl");

    try {
      // 1. START THE TASK (Get Task ID)
      setProgress(2);
      const startResponse = await generateAudioStory({
        file,
        mangaName,
        genre,
        season,
        chapterNumber,
        seriesContext,
        pendingJobId,
        onProgress: (detail, current, total) => {
          setProgressDetail(detail || "");
          if (current && total) {
            setProgress(Math.max(2, Math.round((current / total) * 10)));
          }
        },
      });
      const taskId = startResponse.task_id;
      setPendingJobId("");
      console.log("Task started with ID:", taskId);

      // 2. POLL FOR UPDATES (Every 2 seconds)
      let hasCompleted = false; // Prevent duplicate execution
      const pollInterval = setInterval(async () => {
        if (hasCompleted) return; // Skip if already processed
        try {
          const statusData = await checkTaskStatus(taskId);
          if (hasCompleted) return; // Check again after async call
          console.log("Task Status:", statusData.state);

          if (statusData.state === 'PROCESSING') {
            // Update progress bar based on real worker progress
            setProgress(statusData.progress || 20);
            if (statusData.detail) setProgressDetail(statusData.detail);
          }
          else if (statusData.state === 'SUCCESS') {
            hasCompleted = true; // Mark as completed immediately
            clearInterval(pollInterval);
            setProgress(100);
            console.log(" FULL BACKEND RESPONSE:", statusData);
            console.log("RESULT OBJECT:", statusData.result);
            console.log("IMAGE URLS:", statusData.result?.image_urls);
            let finalResult = statusData.result;

            setStoryData(finalResult);
            // Handle both naming conventions just in case
            if (typeof finalResult === "string" && finalResult.startsWith("http")) {
              console.log(" Downloading Result JSON from:", finalResult);
              try {
                const response = await fetch(finalResult);
                finalResult = await response.json(); // <--- THIS GETS THE REAL DATA
              } catch (fetchErr) {
                console.error("Failed to fetch result JSON", fetchErr);
                showToast.error("Failed to load result data");
                return;
              }
            }
            const images = finalResult.image_urls || finalResult.panel_images || [];
            setPanelImages(images);
            const panelCount = (finalResult.final_video_segments || []).length || images.length;

            // Save to session
            sessionStorage.setItem("pendingStory", JSON.stringify(finalResult));
            sessionStorage.setItem("pendingFileName", mangaName);

            setTimeout(() => {
              setIsProcessing(false);
            }, 500);

            showToast.successLong(`Story Ready! ${panelCount} panels, ${finalResult.total_duration}s duration. Click "Generate Video" to create final video!`);
          }
          else if (statusData.state === 'FAILURE') {
            hasCompleted = true; // Mark as completed immediately
            clearInterval(pollInterval);
            const failureMessage = statusData.error || "Generation Failed";
            setError(failureMessage);
            setIsProcessing(false);
            showToast.error(failureMessage);
          }
        } catch (err) {
          console.error("Polling Error:", err);
          // Stop on a deliberate backend error; transient fetch failures may retry.
          if (err instanceof ApiError) {
            clearInterval(pollInterval);
            hasCompleted = true;
            setError(err.message);
            setIsProcessing(false);
            showToast.error(err.message);

            if (err.status === 401) {
              await logout().catch(() => {});
              navigate("/login", {
                replace: true,
                state: { from: { pathname: location.pathname } },
              });
            }
          }
        }
      }, 2000); // Check every 2 seconds

    } catch (err) {
      console.error("Story generation initiation error:", err);
      if (err instanceof ApiError && err.pendingJobId) {
        setPendingJobId(err.pendingJobId);
      }
      setError(err.message || String(err));
      setIsProcessing(false);
      setProgress(0);
      showToast.error(err.message || "Story generation failed");

        if (err instanceof ApiError && err.status === 401) {
          showToast.error(
            "The API rejected your login token. Sign in again, or check Firebase service account config on the backend.",
          );
          await logout().catch(() => {});
          navigate("/login", {
            replace: true,
            state: { from: { pathname: location.pathname } },
          });
        }
    }
  };

  const handleGenerateVideo = async () => {
    // 1. Check Login
    if (!user) {
      showToast.info("Login Required. Redirecting...");
      setTimeout(() => navigate("/login", { state: { from: location.pathname } }), 2000);
      return;
    }

    // 2. Check Data
    if (!storyData) {
      setError("Please generate story first");
      showToast.error("Please generate story first");
      return;
    }

    setIsGeneratingVideo(true);
    setVideoProgress(0);
    setVideoLogs([]);
    setError(null);

    try {
      setVideoLogs(prev => [...prev, "Checking story data..."]);

      // ⚡ SMART FIX: If storyData is just a URL string, download the real data NOW
      let validStoryData = storyData;

      if (typeof storyData === 'string' && storyData.startsWith('http')) {
        console.log("📥 storyData is a URL. Fetching actual JSON content...");
        setVideoLogs(prev => [...prev, "Downloading story data from server..."]);

        const response = await fetch(storyData);
        if (!response.ok) throw new Error("Failed to download story data");

        validStoryData = await response.json();

        // Update state so we don't have to fetch again
        setStoryData(validStoryData);
        sessionStorage.setItem("pendingStory", JSON.stringify(validStoryData));
        console.log("✅ Data downloaded and saved:", validStoryData);
      }

      // 🔍 DEBUG: Log exactly what we are working with now
      console.log("🎬 STARTING VIDEO GENERATION WITH:", validStoryData);

      // 3. Prepare Variables safely
      const safeScenes = validStoryData.final_video_segments || [];
      const safeImages = validStoryData.image_urls || validStoryData.panel_images || [];
      const safeAudio = validStoryData.audio_url;

      if (!safeImages || safeImages.length === 0) throw new Error("No images found in story data!");
      if (!safeScenes || safeScenes.length === 0) throw new Error("No scenes found in story data!");
      if (!safeAudio) throw new Error("No audio URL found!");

      console.log(`Sending: ${safeImages.length} Images, ${safeScenes.length} Scenes`);
      setVideoLogs(prev => [...prev, `Found ${safeImages.length} images and audio.`]);

      sessionStorage.setItem("isGeneratingVideo", "true");
      sessionStorage.setItem("videoProgress", "0");
      sessionStorage.setItem("videoLogs", JSON.stringify([]));

      // 4. Call Generator
      const result = await generateVideoFromScenes({
        // Standard names
        imageUrls: safeImages,
        audioUrl: safeAudio,
        scenes: safeScenes,

        // Fallback names
        images: safeImages,
        segments: safeScenes,

        // Callbacks
        onProgress: (p) => {
          const safeProgress = Math.min(Math.floor(p), 100);
          setVideoProgress(prev => {
            const newProgress = Math.max(prev, safeProgress);
            sessionStorage.setItem("videoProgress", newProgress.toString());
            return newProgress;
          });
        },
        onLog: (msg) => {
          console.log("[VideoMaker]", msg);
          setVideoLogs(prev => {
            const newLogs = [...prev, msg];
            sessionStorage.setItem("videoLogs", JSON.stringify(newLogs));
            return newLogs;
          });
        },
      });

      // 5. Success Handling
      setVideoUrl(result.videoUrl);
      setVideoBlob(result.blob);
      setVideoProgress(100);
      sessionStorage.setItem("videoProgress", "100");

      setTimeout(() => {
        setIsGeneratingVideo(false);
        sessionStorage.removeItem("isGeneratingVideo");
      }, 500);

      showToast.success("Video generated successfully!");

    } catch (err) {
      console.error("Video generation error:", err);
      setError(err.message || "Video generation failed");
      setIsGeneratingVideo(false);
      showToast.error(err.message || "Video generation failed");
    }
  };
  const formatSize = (bytes) => {
    if (!bytes) return "0 Bytes";
    const sizes = ["Bytes", "KB", "MB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(2) + " " + sizes[i];
  };

  // Enhanced download handler with multiple fallback methods
  const handleDownload = async () => {
    if (isDownloading) return;

    setIsDownloading(true);
    const fileName = `${mangaName || 'manga-video'}.mp4`;

    try {
      // Method 1: Try using the stored blob first
      if (videoBlob) {
        console.log("Downloading using stored blob...");
        try {
          const url = URL.createObjectURL(videoBlob);
          const a = document.createElement('a');
          a.style.display = 'none';
          a.href = url;
          a.download = fileName;
          document.body.appendChild(a);
          a.click();

          // Cleanup
          setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
          }, 100);

          showToast.successBottom("Video downloaded successfully!");
          setIsDownloading(false);
          return;
        } catch (err) {
          console.warn("Blob download failed, trying alternative method:", err);
        }
      }

      // Method 2: Try fetching from the video URL
      if (videoUrl) {
        console.log("Downloading by fetching video URL...");
        try {
          const response = await fetch(videoUrl);
          const blob = await response.blob();

          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.style.display = 'none';
          a.href = url;
          a.download = fileName;
          document.body.appendChild(a);
          a.click();

          // Cleanup
          setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
          }, 100);

          // Store the blob for future downloads
          setVideoBlob(blob);

          showToast.successBottom("Video downloaded successfully!");
          setIsDownloading(false);
          return;
        } catch (err) {
          console.warn("URL fetch download failed, trying direct link:", err);
        }
      }

      // Method 3: Try direct download link
      if (videoUrl) {
        console.log("Attempting direct download link...");
        const a = document.createElement('a');
        a.style.display = 'none';
        a.href = videoUrl;
        a.download = fileName;
        a.target = '_blank';
        document.body.appendChild(a);
        a.click();

        setTimeout(() => {
          document.body.removeChild(a);
        }, 100);

        showToast.successBottom("Download initiated!");
        setIsDownloading(false);
        return;
      }

      // If all methods fail
      throw new Error("No video available for download");

    } catch (err) {
      console.error("Download error:", err);
      showToast.error("Failed to download video. Please try again.");
      setIsDownloading(false);
    }
  };

  return (
    <main className="relative w-full min-h-screen text-white px-3 sm:px-4 md:px-6 lg:px-8 py-6 sm:py-8 overflow-hidden">
      {/* Background gradients */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-64 h-64 sm:w-80 sm:h-80 lg:w-96 lg:h-96 bg-purple-600/10 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-1/3 right-1/3 w-64 h-64 sm:w-80 sm:h-80 lg:w-96 lg:h-96 bg-purple-800/10 rounded-full blur-3xl animate-pulse" />
      </div>

      <div className="grid lg:grid-cols-3 gap-4 sm:gap-5 md:gap-6 mb-6 sm:mb-8 lg:mb-10 max-w-7xl mx-auto relative">
        {/* Main upload area */}
        <div className="lg:col-span-2">
          <div
            onDrop={handleDrop}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={(e) => {
              e.preventDefault();
              setIsDragging(false);
            }}
            onClick={() => fileInputRef.current?.click()}
            className={`relative border-2 border-dotted rounded-xl sm:rounded-2xl p-4 sm:p-6 md:p-8 lg:p-10 transition-all duration-300 backdrop-blur-sm ${isDragging
              ? "border-purple-400 bg-purple-500/10 scale-[1.01] sm:scale-[1.02]"
              : file
                ? "border-purple-500 bg-purple-500/5"
                : "border-gray-700 bg-gray-900/30"
              } hover:border-purple-900 cursor-pointer group`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="application/pdf"
              className="hidden"
              onChange={(e) => handleFile(e.target.files[0])}
            />

            {!file ? (
              <div className="flex flex-col items-center justify-center py-6 sm:py-8">
                <div className="w-14 h-14 sm:w-16 sm:h-16 md:w-20 md:h-20 rounded-full bg-purple-500/10 flex items-center justify-center mb-3 sm:mb-4 md:mb-6 group-hover:scale-110 transition-transform">
                  <Upload className="w-7 h-7 sm:w-8 sm:h-8 md:w-10 md:h-10 text-purple-400" />
                </div>
                <p className="text-lg sm:text-xl md:text-2xl font-semibold mb-1 sm:mb-2 text-center px-2">Drop your manga PDF here</p>
                <p className="text-gray-400 text-xs sm:text-sm text-center">or click to browse</p>
                <p className="text-gray-500 text-xs mt-2 sm:mt-3 md:mt-4 text-center">Maximum file size: {MAX_PDF_MB} MB</p>
              </div>
            ) : (
              <div className="flex items-center gap-3 sm:gap-4 md:gap-6">
                <div className="w-10 h-10 sm:w-12 sm:h-12 md:w-16 md:h-16 bg-purple-500/10 rounded-lg sm:rounded-xl flex items-center justify-center flex-shrink-0 border border-purple-500/20">
                  <FileText className="w-5 h-5 sm:w-6 sm:h-6 md:w-8 md:h-8 text-purple-400" />
                </div>

                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm sm:text-base md:text-lg truncate">{file.name}</p>
                  <p className="text-gray-400 text-xs sm:text-sm mt-0.5 sm:mt-1">{formatSize(file.size)}</p>
                </div>

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFile();
                  }}
                  className="p-2 sm:p-2.5 md:p-3 hover:bg-purple-500/10 rounded-lg sm:rounded-xl transition-all hover:scale-110 border border-transparent hover:border-purple-500/20 flex-shrink-0"
                >
                  <Trash className="w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 text-purple-400" />
                </button>
              </div>
            )}
          </div>

          {/* Processing indicator */}
          {isProcessing && (
            <div className="mt-4 sm:mt-5 md:mt-6 bg-gray-900/40 backdrop-blur-md p-4 sm:p-6 md:p-8 border border-purple-500/30 rounded-xl sm:rounded-2xl shadow-2xl">
              <div className="flex items-center gap-2 sm:gap-3 mb-3 sm:mb-4 md:mb-6">
                <Cpu className="w-5 h-5 sm:w-6 sm:h-6 md:w-7 md:h-7 text-purple-400 animate-pulse flex-shrink-0" />
                <h3 className="text-lg sm:text-xl md:text-2xl font-bold">Processing Manga</h3>
              </div>

              <div className="flex justify-between mb-2 sm:mb-3 text-xs sm:text-sm md:text-base">
                <span className="text-gray-300 font-medium">Backend Processing</span>
                <span className="text-purple-400 font-bold text-sm sm:text-base md:text-lg">{progress}%</span>
              </div>

              <div className="h-2 sm:h-2.5 md:h-3 bg-gray-800/50 rounded-full overflow-hidden mb-3 sm:mb-4 md:mb-6">
                <div
                  className="h-full bg-gradient-to-r from-purple-500 via-purple-600 to-purple-700 transition-all duration-500 ease-out relative"
                  style={{ width: `${progress}%` }}
                >
                  <div className="absolute inset-0 bg-white/20 animate-pulse"></div>
                </div>
              </div>

              <div className="flex items-center justify-center gap-2 text-gray-400 text-xs sm:text-sm">
                <Loader2 className="w-3 h-3 sm:w-4 sm:h-4 animate-spin flex-shrink-0" />
                <span className="text-center">{progressDetail || "Extracting panels, running OCR, generating script and audio..."}</span>
              </div>
            </div>
          )}

          {/* Extracted panels */}
          {!isProcessing && panelCards.length > 0 && (
            <div className="mt-4 sm:mt-5 md:mt-6 bg-gray-900/30 backdrop-blur-sm p-3 sm:p-4 md:p-6 rounded-xl sm:rounded-2xl border border-purple-500/20">
              <div className="flex items-center justify-between mb-3 sm:mb-4 md:mb-5 gap-2">
                <h3 className="font-semibold text-sm sm:text-base md:text-lg flex items-center gap-1.5 sm:gap-2 min-w-0">
                  <Film className="w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 text-gray-400 flex-shrink-0" />
                  <span className="truncate">Extracted Panels</span>
                </h3>
                <span className="px-2 sm:px-2.5 md:px-3 py-0.5 sm:py-1 bg-purple-500/10 rounded-full text-xs sm:text-sm text-purple-300 border border-purple-500/20 whitespace-nowrap flex-shrink-0">
                  {panelCards.length} panel{panelCards.length !== 1 ? 's' : ''}
                </span>
              </div>
              <p className="text-xs text-gray-400 mb-3">Click a panel to preview the exact crop.</p>
              <PanelPreviewGrid cards={panelCards} />
            </div>
          )}

          {!isProcessing && chapterStory && (
            <div className="mt-4 sm:mt-5 md:mt-6 bg-gray-900/30 backdrop-blur-sm p-3 sm:p-4 md:p-6 rounded-xl sm:rounded-2xl border border-purple-500/20">
              <h3 className="font-semibold text-sm sm:text-base md:text-lg mb-2">Chapter Story</h3>
              <p className="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap">{chapterStory}</p>
            </div>
          )}

          {/* Error message */}
          {error && (
            <div className="mt-3 sm:mt-4 p-3 sm:p-4 bg-red-500/10 backdrop-blur-sm border border-red-500/30 rounded-lg sm:rounded-xl flex gap-2 sm:gap-3 animate-pulse">
              <AlertCircle className="w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 text-red-400 flex-shrink-0" />
              <p className="text-red-300 text-xs sm:text-sm md:text-base">{error}</p>
            </div>
          )}
        </div>

        {/* Settings sidebar */}
        <div className="bg-gray-900/30 backdrop-blur-sm border border-purple-500/20 rounded-xl sm:rounded-2xl p-4 sm:p-5 md:p-6 h-fit">
          <div className="flex items-center gap-2 sm:gap-3 mb-4 sm:mb-5 md:mb-6">
            <Settings className="w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 text-purple-400 flex-shrink-0" />
            <h3 className="text-base sm:text-lg md:text-xl font-semibold">Settings</h3>
          </div>

          <div className="space-y-3 mb-5">
            <label className="text-xs sm:text-sm text-gray-400 font-medium block">Manhwa name</label>
            <input
              type="text"
              value={mangaName}
              onChange={(e) => setMangaName(e.target.value)}
              placeholder="e.g. Solo Leveling"
              className="w-full rounded-lg border border-gray-700 bg-gray-800/40 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
            />
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-gray-500 block mb-1">Season (optional)</label>
                <input
                  type="text"
                  value={season}
                  onChange={(e) => setSeason(e.target.value)}
                  placeholder="1"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800/40 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">Chapter (optional)</label>
                <input
                  type="text"
                  value={chapterNumber}
                  onChange={(e) => setChapterNumber(e.target.value)}
                  placeholder="5"
                  className="w-full rounded-lg border border-gray-700 bg-gray-800/40 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                />
              </div>
            </div>
            <div>
              <label className="text-xs text-gray-500 block mb-1">Genre (optional)</label>
              <input
                type="text"
                value={genre}
                onChange={(e) => setGenre(e.target.value)}
                placeholder="Action"
                className="w-full rounded-lg border border-gray-700 bg-gray-800/40 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
              />
            </div>
            {(contextLoading || seriesContext) && (
              <div className="rounded-lg border border-purple-500/20 bg-purple-500/5 p-3">
                <p className="text-xs font-medium text-purple-300 mb-1">
                  {contextLoading
                    ? seriesContext
                      ? "Updating context..."
                      : "Fetching series context..."
                    : "Story context"}
                </p>
                <p className="text-xs text-gray-300 leading-relaxed whitespace-pre-wrap">
                  {seriesContext
                    ? seriesContext
                    : contextLoading
                      ? "Searching the web and model knowledge..."
                      : "No context found. Story will use PDF panels only."}
                </p>
                {!contextLoading && seriesContext && (
                  <p className="text-[10px] text-gray-500 mt-1">
                    {contextGrounded ? "Search-grounded" : "Ungrounded"}
                  </p>
                )}
              </div>
            )}
          </div>

          <label className="text-xs sm:text-sm text-gray-400 font-medium mb-2 sm:mb-3 block">Generation Mode</label>
          <div className="space-y-2 sm:space-y-2.5 md:space-y-3">
            {[
              { value: "images", label: "Original Images", icon: FileText, disabled: false },
              { value: "ai", label: "AI Enhanced", icon: Cpu, disabled: true },
              { value: "both", label: "Hybrid Mode", icon: Zap, disabled: true },
            ].map((opt) => (
              <label
                key={opt.value}
                className={`block p-2.5 sm:p-3 md:p-4 rounded-lg sm:rounded-xl border transition-all cursor-pointer ${opt.disabled
                  ? "opacity-50 cursor-not-allowed"
                  : mode === opt.value
                    ? "border-purple-500 bg-purple-500/10"
                    : "border-gray-700 bg-gray-800/30 hover:bg-gray-800/50 hover:border-purple-500/50"
                  }`}
              >
                <div className="flex items-center gap-2 sm:gap-2.5 md:gap-3">
                  <input
                    type="radio"
                    name="mode"
                    value={opt.value}
                    checked={mode === opt.value}
                    onChange={(e) => !opt.disabled && setMode(e.target.value)}
                    disabled={opt.disabled}
                    className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-purple-500 flex-shrink-0"
                  />
                  <opt.icon className="w-4 h-4 sm:w-4 sm:h-4 md:w-5 md:h-5 text-purple-400 flex-shrink-0" />
                  <span className="flex-1 text-xs sm:text-sm md:text-base">{opt.label}</span>
                  {opt.disabled && <Lock className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-gray-500 flex-shrink-0" />}
                </div>
              </label>
            ))}
          </div>

          <div className="mt-4 sm:mt-6 md:mt-8 p-2.5 sm:p-3 md:p-4 bg-purple-500/5 rounded-lg sm:rounded-xl border border-purple-500/20">
            <p className="text-xs sm:text-xs text-gray-400 leading-relaxed">
              <strong className="text-purple-700">Note:</strong> AI Enhanced and Hybrid modes are coming soon. Currently using original manga panels for video generation.
            </p>
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div className="max-w-7xl mx-auto flex flex-col sm:flex-row gap-3 sm:gap-4 md:gap-6 justify-center mb-6 sm:mb-8 lg:mb-10 relative">
        <div className="relative group/story w-full sm:w-auto">
          <button
            onClick={handleGenerateStory}
            disabled={isProcessing || !file || isGeneratingVideo}
            aria-describedby={showSummaryWaitTooltip ? "generate-story-summary-tip" : undefined}
            className={`w-full sm:w-auto px-5 sm:px-6 md:px-8 py-3.5 sm:py-4 md:py-5 rounded-full font-bold text-sm sm:text-base md:text-lg transition-all flex items-center justify-center gap-2 sm:gap-2.5 md:gap-3 backdrop-blur-xl border shadow-[0_8px_25px_rgba(255,255,255,0.15)] 
  ${isProcessing || !file || isGeneratingVideo
              ? "opacity-50 cursor-not-allowed bg-white/10 border-white/20"
              : storyData
                ? "bg-gradient-to-r from-purple-400 via-purple-400 to-indigo-500 text-white hover:from-purple-500 hover:to-purple-700 border-gray-400/50 hover:scale-105 active:scale-95"
                : "bg-white/10 border-white/20 hover:bg-white/20 hover:scale-105 active:scale-95"
            }`}
          >
            {isProcessing ? (
              <>
                <Loader2 className="w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 animate-spin flex-shrink-0" />
                <span className="whitespace-nowrap">Processing {progress}%</span>
              </>
            ) : storyData ? (
              <>
                <Cpu className="w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 flex-shrink-0" />
                <span className="whitespace-nowrap">Regenerate Frames</span>
              </>
            ) : (
              <>
                <Cpu className="w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 flex-shrink-0" />
                <span className="whitespace-nowrap">Generate Story</span>
              </>
            )}
          </button>
          {showSummaryWaitTooltip && (
            <div
              id="generate-story-summary-tip"
              role="tooltip"
              className="pointer-events-none absolute left-1/2 bottom-full z-30 mb-3 w-[min(19rem,calc(100vw-2rem))] -translate-x-1/2 opacity-0 translate-y-1 scale-95 transition-all duration-200 group-hover/story:opacity-100 group-hover/story:translate-y-0 group-hover/story:scale-100 group-focus-within/story:opacity-100 group-focus-within/story:translate-y-0 group-focus-within/story:scale-100"
            >
              <div className="rounded-2xl border border-purple-400/40 bg-gray-950/95 px-4 py-3 text-left shadow-[0_16px_40px_rgba(168,85,247,0.35)] backdrop-blur-xl">
                <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-purple-300">
                  <Info className="h-3.5 w-3.5 shrink-0" />
                  Summary not ready
                </p>
                <p className="mt-1.5 text-xs sm:text-sm leading-relaxed text-gray-200">
                  Please wait until the summary is generated. That will make your story better.
                </p>
              </div>
              <div className="mx-auto -mt-1.5 h-3 w-3 rotate-45 border-r border-b border-purple-400/40 bg-gray-950/95" />
            </div>
          )}
        </div>

        <button
          onClick={handleGenerateVideo}
          disabled={!storyData || isGeneratingVideo}
          className={`w-full sm:w-auto px-5 sm:px-6 md:px-8 py-3.5 sm:py-4 md:py-5 rounded-full font-bold text-sm sm:text-base md:text-lg transition-all flex items-center justify-center gap-2 sm:gap-2.5 md:gap-3 backdrop-blur-xl border shadow-[0_8px_25px_rgba(255,255,255,0.15)] 
  ${!storyData || isGeneratingVideo
              ? "opacity-50 cursor-not-allowed bg-white/10 border-white/20"
              : videoUrl
                ? "bg-gradient-to-r from-purple-400 via-purple-400/80 to-indigo-500 text-white hover:from-purple-500 hover:to-purple-700 border-gray-400/50 hover:scale-105 active:scale-95"
                : "bg-gradient-to-r from-purple-400 via-purple-400/80 to-indigo-500 text-white hover:from-purple-500 hover:to-purple-700 border-gray-400/50 hover:scale-105 active:scale-95"
            }`}
        >
          {isGeneratingVideo ? (
            <>
              <Loader2 className="w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 animate-spin flex-shrink-0" />
              <span className="whitespace-nowrap">Generating {videoProgress}%</span>
            </>
          ) : videoUrl ? (
            <>
              <Video className="w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 flex-shrink-0" />
              <span className="whitespace-nowrap hidden sm:inline">Generate Video Again</span>
              <span className="whitespace-nowrap sm:hidden">Regenerate Video</span>
            </>
          ) : (
            <>
              <Video className="w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 flex-shrink-0" />
              <span className="whitespace-nowrap">Generate Video</span>
            </>
          )}
        </button>
      </div>

      {/* Video generation progress */}
      {isGeneratingVideo && (
        <div className="max-w-7xl mx-auto mb-6 sm:mb-8 lg:mb-10 relative">
          <div className="bg-gradient-to-br from-purple-900/20 via-purple-800/10 to-purple-900/20 backdrop-blur-xl p-4 sm:p-6 md:p-8 border border-purple-500/30 rounded-xl sm:rounded-2xl shadow-2xl">
            <div className="flex items-center gap-2 sm:gap-3 mb-3 sm:mb-4 md:mb-6">
              <Video className="w-5 h-5 sm:w-6 sm:h-6 md:w-7 md:h-7 text-purple-500 animate-pulse flex-shrink-0" />
              <h3 className="text-lg sm:text-xl md:text-2xl font-bold">Generating Video</h3>
            </div>

            <div className="flex justify-between mb-2 sm:mb-3 text-xs sm:text-sm md:text-base">
              <span className="text-gray-300 font-medium">Browser Processing</span>
              <span className="text-white font-bold text-sm sm:text-base md:text-lg">{videoProgress}%</span>
            </div>

            <div className="relative h-2.5 sm:h-3 md:h-4 bg-black/40 backdrop-blur-sm rounded-full overflow-hidden mb-3 sm:mb-4 md:mb-6 border border-purple-500/20">
              <div className="absolute inset-0 bg-gradient-to-r from-purple-500/10 via-purple-400/10 to-purple-500/10"></div>
              <div
                className="relative h-full bg-gradient-to-r from-pink-400/50 via-purple-500/50 to-purple-700/60 transition-all duration-300 ease-out"
                style={{ width: `${videoProgress}%` }}
              >
                <div className="absolute inset-0 bg-gradient-to-b from-white/30 via-white/10 to-transparent"></div>
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/20 to-transparent animate-shimmer"></div>
                <div className="absolute inset-0 shadow-[inset_0_1px_1px_rgba(255,255,255,0.3)]"></div>
              </div>
              <div
                className="absolute top-0 left-0 h-full bg-purple-400/30 blur-md transition-all duration-300 ease-out"
                style={{ width: `${videoProgress}%` }}
              ></div>
            </div>

            <div className="bg-black/60 backdrop-blur-sm rounded-lg sm:rounded-xl p-3 sm:p-4 md:p-5 max-h-32 sm:max-h-40 md:max-h-48 overflow-y-auto border border-purple-500/10 mb-3 sm:mb-4">
              {videoLogs.map((log, idx) => (
                <div key={idx} className="text-xs sm:text-sm text-purple-300 font-mono mb-1.5 sm:mb-2 flex items-start gap-1.5 sm:gap-2">
                  <span className="text-purple-500 flex-shrink-0">&gt;</span>
                  <span className="break-all">{log}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Video player */}
      {videoUrl && !isGeneratingVideo && (
        <div className="max-w-7xl mx-auto mb-12 sm:mb-16 md:mb-20 relative">
          <div
            ref={videoContainerRef}
            className="bg-gradient-to-br from-gray-900/10 via-black/10 to-gray-900/10 rounded-xl sm:rounded-2xl overflow-hidden shadow-2xl border border-purple-500/30"
          >
            <div className="p-4 sm:p-5 md:p-6 border-b border-purple-500/20 bg-gradient-to-r from-purple-900/30 via-purple-800/20 to-purple-900/30 backdrop-blur-sm">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 sm:gap-4">
                <div className="flex items-center gap-2 sm:gap-3 min-w-0 w-full sm:w-auto">
                  <div className="w-8 h-8 sm:w-9 sm:h-9 md:w-10 md:h-10 rounded-full bg-gradient-to-br from-purple-400 to-transparent flex items-center justify-center flex-shrink-0">
                    <CheckCircle className="w-4 h-4 sm:w-5 sm:h-5 md:w-6 md:h-6 text-white" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="text-base sm:text-xl md:text-2xl font-bold text-white truncate">Video Ready</h3>
                    <p className="text-xs sm:text-sm text-gray-400 truncate">
                      Your manga video has been generated successfully
                    </p>
                  </div>
                </div>

                <div className="flex gap-2 sm:gap-3 w-full sm:w-auto justify-end">
                  <button
                    onClick={handleDownload}
                    disabled={isDownloading}
                    className={`flex-1 sm:flex-initial px-4 sm:px-5 md:px-6 py-2 sm:py-2.5 md:py-3 rounded-lg bg-gradient-to-r from-purple-500 to-purple-600 hover:from-purple-600 hover:to-purple-700 backdrop-blur-md transition-all flex items-center justify-center gap-2 border border-purple-400/20 shadow-lg hover:scale-105 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100`}
                    title="Download Video"
                  >
                    {isDownloading ? (
                      <>
                        <Loader2 className="w-4 h-4 sm:w-5 sm:h-5 animate-spin" />
                        <span className="text-sm font-semibold">Downloading...</span>
                      </>
                    ) : (
                      <>
                        <Download className="w-4 h-4 sm:w-5 sm:h-5" />
                        <span className="text-sm font-semibold">Download</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>

            <div className="relative bg-black overflow-hidden group">
              <div className="relative w-full h-0" style={{ paddingTop: '56.25%' }}>
                <div className="absolute inset-0 overflow-hidden">
                  <video
                    className="absolute top-0 left-0 w-full h-full object-cover blur-3xl scale-110 opacity-40"
                    src={videoUrl}
                    muted
                  />
                </div>
                <video
                  ref={videoRef}
                  controls
                  className="absolute top-0 left-0 w-full h-full object-cover z-10"
                  controlsList="nodownload"
                  style={{ objectFit: 'cover' }}
                >
                  <source src={videoUrl} type="video/mp4" />
                  Your browser does not support the video tag.
                </video>
              </div>
            </div>

            <div className="hidden md:block bg-gradient-to-r from-transparent via-black/40 to-transparent border-t border-purple-500/20 p-3 sm:p-4 md:p-5">
              <div className="flex flex-wrap items-center justify-center gap-3 sm:gap-4 md:gap-8 text-xs sm:text-sm text-gray-300">
                <div className="flex items-center gap-1.5 sm:gap-2 px-2 sm:px-3 py-1 sm:py-1.5 rounded-full bg-transparent">
                  <Film className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-yellow-400 flex-shrink-0" />
                  <span className="whitespace-nowrap">Browser Generated</span>
                </div>
                <div className="flex items-center gap-1.5 sm:gap-2 px-2 sm:px-3 py-1 sm:py-1.5 rounded-full bg-transparent">
                  <Zap className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-yellow-400 flex-shrink-0" />
                  <span className="whitespace-nowrap">Zero Server Cost</span>
                </div>
                <div className="flex items-center gap-1.5 sm:gap-2 px-2 sm:px-3 py-1 sm:py-1.5 rounded-full bg-transparent">
                  <Cpu className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-yellow-400 flex-shrink-0" />
                  <span className="whitespace-nowrap">FFmpeg.wasm</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </main>
  );
};

export default UploadPage;
