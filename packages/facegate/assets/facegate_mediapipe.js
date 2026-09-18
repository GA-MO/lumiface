const TASKS_VISION = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@1.0.1";
const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

const NOSE_TIP = 1;
const RIGHT_EYE = [33, 133, 159, 145];
const LEFT_EYE = [362, 263, 386, 374];

function centre(landmarks, indices) {
  let x = 0;
  let y = 0;
  for (const i of indices) {
    x += landmarks[i].x;
    y += landmarks[i].y;
  }
  return [x / indices.length, y / indices.length];
}

function boundingBox(landmarks) {
  let minX = 1, minY = 1, maxX = 0, maxY = 0;
  for (const p of landmarks) {
    if (p.x < minX) minX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.x > maxX) maxX = p.x;
    if (p.y > maxY) maxY = p.y;
  }
  return [minX, minY, maxX - minX, maxY - minY];
}

function blendshape(list, name) {
  const hit = list.find((c) => c.categoryName === name);
  return hit ? hit.score : null;
}

function anglesFromMatrix(m) {
  const deg = 180 / Math.PI;
  const yaw = Math.atan2(m[8], m[10]) * deg;
  const pitch = Math.atan2(-m[9], m[10]) * deg;
  return [yaw, pitch];
}

function faceFromResult(result, i) {
  const landmarks = result.faceLandmarks[i];
  const shapes = result.faceBlendshapes?.[i]?.categories ?? [];
  const matrix = result.facialTransformationMatrixes?.[i]?.data;
  const [yaw, pitch] = matrix ? anglesFromMatrix(matrix) : [null, null];
  const blinkLeft = blendshape(shapes, "eyeBlinkLeft");
  const blinkRight = blendshape(shapes, "eyeBlinkRight");
  const smileLeft = blendshape(shapes, "mouthSmileLeft");
  const smileRight = blendshape(shapes, "mouthSmileRight");
  return {
    box: boundingBox(landmarks),
    eyeOpenLeft: blinkLeft == null ? null : 1 - blinkLeft,
    eyeOpenRight: blinkRight == null ? null : 1 - blinkRight,
    smile: smileLeft == null || smileRight == null ? null : (smileLeft + smileRight) / 2,
    yaw,
    pitch,
    nose: [landmarks[NOSE_TIP].x, landmarks[NOSE_TIP].y],
    leftEye: centre(landmarks, LEFT_EYE),
    rightEye: centre(landmarks, RIGHT_EYE),
  };
}

async function create(options = {}) {
  const base = options.tasksVisionUrl ?? TASKS_VISION;
  const { FaceLandmarker, FilesetResolver } = await import(`${base}/vision_bundle.mjs`);
  const vision = await FilesetResolver.forVisionTasks(`${base}/wasm`);
  const landmarker = await FaceLandmarker.createFromOptions(vision, {
    baseOptions: { modelAssetPath: options.modelUrl ?? MODEL_URL, delegate: options.delegate ?? "GPU" },
    runningMode: "VIDEO",
    numFaces: 2,
    outputFaceBlendshapes: true,
    outputFacialTransformationMatrixes: true,
  });
  return {
    detect(video, timestampMs) {
      if (video.readyState < 2) return JSON.stringify({ faces: [] });
      const result = landmarker.detectForVideo(video, timestampMs);
      const faces = result.faceLandmarks.map((_, i) => faceFromResult(result, i));
      faces.sort((a, b) => b.box[2] * b.box[3] - a.box[2] * a.box[3]);
      return JSON.stringify({ faces });
    },
    close() {
      landmarker.close();
    },
  };
}

function captureJpeg(video, quality) {
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) return reject(new Error("toBlob failed"));
      blob.arrayBuffer().then(resolve, reject);
    }, "image/jpeg", quality);
  });
}

window.facegateMediaPipe = { create, captureJpeg };
