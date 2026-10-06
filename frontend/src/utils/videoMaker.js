import * as Mp4Muxer from 'mp4-muxer';

// =====================================================================
// Constants (Optimized for Speed & Stability)
// =====================================================================
// ⚡ FIX 1: 720p fits within the 'Level 3.1' codec limit (fixing NotSupportedError)
const CANVAS_WIDTH = 720;
const CANVAS_HEIGHT = 1280;
// ⚡ FIX 2: 24 FPS is standard for Anime and 20% faster to render than 30 FPS
const FPS = 24; 
const VIDEO_BITRATE = 2_500_000; // 2.5 Mbps

// =====================================================================
// Helpers
// =====================================================================
async function downloadImage(url, filename, retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.blob(); 
    } catch (error) {
      if (i === retries - 1) throw error;
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
}

// =====================================================================
// Canvas Drawer (Zoom/Pan Logic)
// =====================================================================
function normalizeCrop(img, panelBBox) {
  if (!Array.isArray(panelBBox) || panelBBox.length !== 4) {
    return { x: 0, y: 0, width: img.width, height: img.height };
  }

  const [x1, y1, x2, y2] = panelBBox.map(Number);
  const x = Math.max(0, Math.min(x1, img.width - 1));
  const y = Math.max(0, Math.min(y1, img.height - 1));
  const width = Math.max(1, Math.min(x2, img.width) - x);
  const height = Math.max(1, Math.min(y2, img.height) - y);
  return { x, y, width, height };
}

function drawFrameToCanvas(ctx, img, crop, progress, type) {
  const imgW = crop.width;
  const imgH = crop.height;
  
  // Clear background
  ctx.fillStyle = 'black';
  ctx.fillRect(0, 0, CANVAS_WIDTH, CANVAS_HEIGHT);

  const contentWidth = Math.floor(CANVAS_WIDTH * 1.0);
  const destX = (CANVAS_WIDTH - contentWidth) / 2; 

  if (type === 'pan_down') {
    const scale = contentWidth / imgW;
    const scaledH = imgH * scale;
    const destH = CANVAS_HEIGHT; 
    const hiddenHeight = scaledH - destH;
    
    let drawY = 0 - (hiddenHeight * progress);
    if (hiddenHeight <= 0) drawY = (CANVAS_HEIGHT - scaledH) / 2;

    ctx.drawImage(
      img,
      crop.x, crop.y, crop.width, crop.height,
      destX, drawY, contentWidth, scaledH,
    );
  } 
  else {
    // Zoom Effect
    const zoomLevel = 1.0 + (0.15 * progress); 
    const srcW = imgW / zoomLevel;
    const srcH = imgH / zoomLevel;
    const srcX = crop.x + ((imgW - srcW) / 2);
    const srcY = crop.y + ((imgH - srcH) / 2);

    const imgAspect = imgW / imgH;
    let drawW = contentWidth;
    let drawH = contentWidth / imgAspect;
    const drawY = (CANVAS_HEIGHT - drawH) / 2;

    ctx.drawImage(img, srcX, srcY, srcW, srcH, destX, drawY, drawW, drawH);
  }
}

function determineEffectType(crop) {
  const imageAspect = crop.height / crop.width;
  const contentAspect = CANVAS_HEIGHT / CANVAS_WIDTH;
  return (imageAspect > contentAspect * 1.5) ? 'pan_down' : 'zoom';
}

// =====================================================================
// Audio Processor
// =====================================================================
async function loadAudio(audioUrl) {
  const response = await fetch(audioUrl);
  if (!response.ok) throw new Error(`Audio download failed: HTTP ${response.status}`);
  const arrayBuffer = await response.arrayBuffer();
  const audioCtx = new AudioContext();
  const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer);
  await audioCtx.close();
  return audioBuffer;
}

async function processAudio(audioBuffer, muxer) {
  const audioEncoder = new AudioEncoder({
    output: (chunk, meta) => muxer.addAudioChunk(chunk, meta),
    error: (e) => console.error(e)
  });

  audioEncoder.configure({
    codec: 'mp4a.40.2', 
    numberOfChannels: audioBuffer.numberOfChannels,
    sampleRate: audioBuffer.sampleRate,
    bitrate: 128000
  });

  const numberOfChannels = audioBuffer.numberOfChannels;
  const length = audioBuffer.length;
  const sampleRate = audioBuffer.sampleRate;
  const chunkSize = sampleRate * 1; 
  
  for (let frame = 0; frame < length; frame += chunkSize) {
    const size = Math.min(chunkSize, length - frame);
    const data = new Float32Array(size * numberOfChannels);
    
    for (let ch = 0; ch < numberOfChannels; ch++) {
      const channelData = audioBuffer.getChannelData(ch);
      for (let i = 0; i < size; i++) {
        data[i * numberOfChannels + ch] = channelData[frame + i];
      }
    }

    const audioData = new AudioData({
      format: 'f32',
      sampleRate: sampleRate,
      numberOfChannels: numberOfChannels,
      numberOfFrames: size,
      timestamp: (frame / sampleRate) * 1_000_000,
      data: data
    });

    audioEncoder.encode(audioData);
    audioData.close();
    
    // Yield to keep UI responsive
    await new Promise(r => setTimeout(r, 0));
  }

  await audioEncoder.flush();
}

// =====================================================================
// MAIN FUNCTION (Optimized)
// =====================================================================
export async function generateVideoFromScenes({
  imageUrls,
  audioUrl,
  scenes,
  onProgress,
  onLog,
}) {
  const log = (msg) => { console.log(msg); if (onLog) onLog(msg); };

  try {
    log('[WebCodecs] Starting optimized generation...');

    if (!Array.isArray(scenes) || scenes.length === 0) {
      throw new Error('No video segments were provided');
    }

    const audioBuffer = audioUrl ? await loadAudio(audioUrl) : null;

    const muxer = new Mp4Muxer.Muxer({
      target: new Mp4Muxer.ArrayBufferTarget(),
      video: { codec: 'avc', width: CANVAS_WIDTH, height: CANVAS_HEIGHT },
      ...(audioBuffer ? {
        audio: {
          codec: 'aac',
          numberOfChannels: audioBuffer.numberOfChannels,
          sampleRate: audioBuffer.sampleRate,
        },
      } : {}),
      fastStart: 'in-memory',
    });

    const videoEncoder = new VideoEncoder({
      output: (chunk, meta) => muxer.addVideoChunk(chunk, meta),
      error: (e) => console.error('[VideoEncoder]', e)
    });

    // ⚡ FIX 1: This codec settings works perfectly with 720p
    videoEncoder.configure({
      codec: 'avc1.42001f', 
      width: CANVAS_WIDTH,
      height: CANVAS_HEIGHT,
      bitrate: VIDEO_BITRATE,
      framerate: FPS
    });

    const canvas = new OffscreenCanvas(CANVAS_WIDTH, CANVAS_HEIGHT);
    const ctx = canvas.getContext('2d');

    // 1. Preload Images
    log('[Download] Fetching assets...');
    const imageBitmaps = [];
    for (let i = 0; i < imageUrls.length; i++) {
      const blob = await downloadImage(imageUrls[i]);
      const bmp = await createImageBitmap(blob);
      imageBitmaps.push(bmp);
    }

    let renderedFrames = 0;
    
    // 2. Render Loop (Optimized)
    for (let i = 0; i < scenes.length; i++) {
      const scene = scenes[i];
      let imgIdx = scene.image_page_index ?? (i % imageBitmaps.length);
      if (typeof imgIdx !== 'number' || isNaN(imgIdx)) imgIdx = i % imageBitmaps.length;
      imgIdx = Math.min(imgIdx, imageBitmaps.length - 1);

      const img = imageBitmaps[imgIdx];
      const crop = normalizeCrop(img, scene.panel_bbox);
      const effectType = scene.animation_type || determineEffectType(crop);
      const fallbackStart = renderedFrames / FPS;
      const startTime = Number.isFinite(Number(scene.start_time))
        ? Number(scene.start_time)
        : fallbackStart;
      const durationSec = Number(scene.duration) > 0 ? Number(scene.duration) : 3.0;
      const endTime = Number.isFinite(Number(scene.end_time))
        ? Number(scene.end_time)
        : startTime + durationSec;
      const startFrame = Math.max(renderedFrames, Math.round(startTime * FPS));
      const endFrame = Math.max(startFrame + 1, Math.round(endTime * FPS));
      const totalFrames = endFrame - startFrame;

      log(`[Render] Scene ${i + 1}/${scenes.length}: ${durationSec}s (${totalFrames} frames)`);

      for (let frame = 0; frame < totalFrames; frame++) {
        const progress = frame / totalFrames;

        drawFrameToCanvas(ctx, img, crop, progress, effectType);

        const videoFrame = new VideoFrame(canvas, {
          timestamp: (renderedFrames * 1_000_000) / FPS,
          duration: 1000000 / FPS 
        });

        // ⚡ FIX 2: Prevent "Codec reclaimed" by pausing if queue is full
        if (videoEncoder.encodeQueueSize > 5) {
           await new Promise(r => setTimeout(r, 5));
        }

        videoEncoder.encode(videoFrame, { keyFrame: frame % 60 === 0 });
        videoFrame.close();

        renderedFrames += 1;
        
        // ⚡ FIX 3: Critical yield to Main Thread to prevent browser hang
        if (frame % 10 === 0) {
           await new Promise(r => setTimeout(r, 0));
        }
      }
      
      if (onProgress) onProgress(((i+1) / scenes.length) * 80);
    }

    // 3. Audio Encoding
    if (audioBuffer) {
      log('[Audio] Mixing audio...');
      try {
        await processAudio(audioBuffer, muxer);
      } catch (e) {
        log('[Audio] Error: ' + e.message);
      }
    }

    log('[Finalize] Saving video...');
    await videoEncoder.flush();
    muxer.finalize();

    const { buffer } = muxer.target;
    const blob = new Blob([buffer], { type: 'video/mp4' });
    const videoUrl = URL.createObjectURL(blob);

    imageBitmaps.forEach(bmp => bmp.close());

    if (onProgress) onProgress(100);
    log('[Done] Video created!');

    return { videoUrl, blob, duration: renderedFrames / FPS };

  } catch (error) {
    console.error(error);
    throw error;
  }
}

// =====================================================================
// Download Helper
// =====================================================================
export function downloadVideo(blob, filename = 'manhwa_video.mp4') {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
