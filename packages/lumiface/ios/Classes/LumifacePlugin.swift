import CoreVideo
import Flutter
import Vision

/// `ai.lumiface/detector`: Apple Vision face rectangles on every camera frame the Dart side sends and, while
/// recording, the same frame through the H.264 encoder. `process` answers with the faces (top-left
/// normalised boxes; yaw and roll on every OS, pitch from iOS 15) and the access units finished so far;
/// `stopRecording` flushes the encoder.
public class LumifacePlugin: NSObject, FlutterPlugin {
  private let queue = DispatchQueue(label: "ai.lumiface.detector")
  private var encoder: H264Encoder?

  public static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(name: "ai.lumiface/detector", binaryMessenger: registrar.messenger())
    registrar.addMethodCallDelegate(LumifacePlugin(), channel: channel)
  }

  public func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    switch call.method {
    case "process":
      process(call, result: result)
    case "stopRecording":
      queue.async {
        let chunks = self.encoder?.finish() ?? []
        self.encoder = nil
        DispatchQueue.main.async { result(chunks.map(LumifacePlugin.chunkMap)) }
      }
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  private func process(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    guard let args = call.arguments as? [String: Any],
          let data = args["bytes"] as? FlutterStandardTypedData,
          let width = args["width"] as? Int,
          let height = args["height"] as? Int,
          let bytesPerRow = args["bytesPerRow"] as? Int,
          args["format"] as? String == "bgra8888"
    else {
      result(FlutterError(code: "BAD_FRAME", message: "expected bgra8888 bytes, width, height, bytesPerRow", details: nil))
      return
    }
    let rotation = args["rotation"] as? Int ?? 0
    let mirror = args["mirror"] as? Bool ?? false
    let ts = Int64((args["ts"] as? NSNumber)?.int64Value ?? 0)
    let record = args["record"] as? Bool ?? false
    let bytes = data.data
    queue.async {
      do {
        let (buffer, faces) = try LumifacePlugin.detect(bytes: bytes, width: width, height: height, bytesPerRow: bytesPerRow, rotation: rotation)
        var chunks: [[String: Any]] = []
        if record {
          if self.encoder == nil { self.encoder = H264Encoder(width: width, height: height) }
          if let enc = self.encoder { chunks = enc.encode(buffer, mirror: mirror, ts: ts).map(LumifacePlugin.chunkMap) }
        }
        DispatchQueue.main.async { result(["faces": faces, "chunks": chunks]) }
      } catch {
        DispatchQueue.main.async { result(FlutterError(code: "DETECT_FAILED", message: error.localizedDescription, details: nil)) }
      }
    }
  }

  private static func chunkMap(_ c: Chunk) -> [String: Any] {
    ["ts": c.ts, "data": FlutterStandardTypedData(bytes: c.data)]
  }

  private static func orientation(_ rotation: Int) -> CGImagePropertyOrientation {
    switch rotation {
    case 90: return .right
    case 180: return .down
    case 270: return .left
    default: return .up
    }
  }

  /// The frame as a pixel buffer of its own (the encoder keeps it past this call) and Vision's faces on it.
  static func detect(bytes: Data, width: Int, height: Int, bytesPerRow: Int, rotation: Int) throws -> (CVPixelBuffer, [[String: Double]]) {
    var pixelBuffer: CVPixelBuffer?
    let attrs: [CFString: Any] = [kCVPixelBufferIOSurfacePropertiesKey: [:]]
    guard CVPixelBufferCreate(kCFAllocatorDefault, width, height, kCVPixelFormatType_32BGRA, attrs as CFDictionary, &pixelBuffer) == kCVReturnSuccess,
          let buffer = pixelBuffer else {
      throw NSError(domain: "ai.lumiface", code: 1, userInfo: [NSLocalizedDescriptionKey: "CVPixelBufferCreate failed"])
    }
    CVPixelBufferLockBaseAddress(buffer, [])
    if let dst = CVPixelBufferGetBaseAddress(buffer) {
      let dstRow = CVPixelBufferGetBytesPerRow(buffer)
      bytes.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
        guard let src = raw.baseAddress else { return }
        if dstRow == bytesPerRow {
          memcpy(dst, src, min(raw.count, dstRow * height))
        } else {
          for y in 0..<height { memcpy(dst + y * dstRow, src + y * bytesPerRow, min(bytesPerRow, dstRow)) }
        }
      }
    }
    CVPixelBufferUnlockBaseAddress(buffer, [])
    let request = VNDetectFaceRectanglesRequest()
    if #available(iOS 15.0, *) {
      request.revision = VNDetectFaceRectanglesRequestRevision3
    }
    let handler = VNImageRequestHandler(cvPixelBuffer: buffer, orientation: orientation(rotation), options: [:])
    try handler.perform([request])
    let degrees = 180.0 / Double.pi
    let faces = (request.results ?? []).map { face -> [String: Double] in
      let b = face.boundingBox
      var out: [String: Double] = [
        "left": Double(b.origin.x),
        "top": Double(1 - b.origin.y - b.size.height),
        "width": Double(b.size.width),
        "height": Double(b.size.height),
      ]
      if let yaw = face.yaw { out["yaw"] = yaw.doubleValue * degrees }
      if #available(iOS 15.0, *), let pitch = face.pitch { out["pitch"] = pitch.doubleValue * degrees }
      return out
    }
    return (buffer, faces)
  }
}
