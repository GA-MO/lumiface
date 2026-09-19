import Accelerate
import CoreMedia
import CoreVideo
import Foundation
import VideoToolbox

/// One encoded access unit and the frame time (device ms) it was fed at.
struct Chunk {
  let ts: Int64
  let data: Data
}

/// VideoToolbox H.264 (baseline, no reordering) fed with the camera's BGRA frames, mirrored back when the
/// front camera delivered them mirrored. Output is Annex-B with SPS/PPS in front of every keyframe, one
/// access unit per chunk, carrying the device time it was fed at.
final class H264Encoder {
  private var session: VTCompressionSession?
  private let width: Int
  private let height: Int
  private var pending: [Chunk] = []
  private let lock = NSLock()
  private var mirrorBuffer: CVPixelBuffer?

  init?(width: Int, height: Int) {
    self.width = width
    self.height = height
    var s: VTCompressionSession?
    let status = VTCompressionSessionCreate(
      allocator: nil, width: Int32(width), height: Int32(height), codecType: kCMVideoCodecType_H264,
      encoderSpecification: nil, imageBufferAttributes: nil, compressedDataAllocator: nil,
      outputCallback: nil, refcon: nil, compressionSessionOut: &s)
    guard status == noErr, let session = s else { return nil }
    self.session = session
    VTSessionSetProperty(session, key: kVTCompressionPropertyKey_RealTime, value: kCFBooleanTrue)
    VTSessionSetProperty(session, key: kVTCompressionPropertyKey_ProfileLevel, value: kVTProfileLevel_H264_Baseline_AutoLevel)
    VTSessionSetProperty(session, key: kVTCompressionPropertyKey_AllowFrameReordering, value: kCFBooleanFalse)
    VTSessionSetProperty(session, key: kVTCompressionPropertyKey_MaxKeyFrameInterval, value: 15 as CFNumber)
    VTSessionSetProperty(session, key: kVTCompressionPropertyKey_AverageBitRate, value: 1_500_000 as CFNumber)
    VTSessionSetProperty(session, key: kVTCompressionPropertyKey_ExpectedFrameRate, value: 15 as CFNumber)
    VTCompressionSessionPrepareToEncodeFrames(session)
  }

  /// Feeds one frame and returns the access units finished so far.
  func encode(_ buffer: CVPixelBuffer, mirror: Bool, ts: Int64) -> [Chunk] {
    guard let session = session else { return [] }
    let source = mirror ? (mirrored(buffer) ?? buffer) : buffer
    let pts = CMTime(value: ts, timescale: 1000)
    VTCompressionSessionEncodeFrame(session, imageBuffer: source, presentationTimeStamp: pts, duration: .invalid,
                                    frameProperties: nil, infoFlagsOut: nil) { [weak self] status, _, sample in
      guard status == noErr, let sample = sample, let self = self else { return }
      self.collect(sample)
    }
    return drain()
  }

  /// Flushes the encoder and returns the last access units.
  func finish() -> [Chunk] {
    guard let session = session else { return drain() }
    VTCompressionSessionCompleteFrames(session, untilPresentationTimeStamp: .invalid)
    VTCompressionSessionInvalidate(session)
    self.session = nil
    return drain()
  }

  private func drain() -> [Chunk] {
    lock.lock()
    defer { lock.unlock() }
    let out = pending
    pending.removeAll()
    return out
  }

  private func collect(_ sample: CMSampleBuffer) {
    guard let dataBuffer = CMSampleBufferGetDataBuffer(sample), let format = CMSampleBufferGetFormatDescription(sample) else { return }
    let attachments = CMSampleBufferGetSampleAttachmentsArray(sample, createIfNecessary: false) as? [[CFString: Any]]
    let notSync = attachments?.first?[kCMSampleAttachmentKey_NotSync] as? Bool ?? false
    var out = Data()
    let startCode = Data([0, 0, 0, 1])
    if !notSync {
      var count = 0
      CMVideoFormatDescriptionGetH264ParameterSetAtIndex(format, parameterSetIndex: 0, parameterSetPointerOut: nil,
                                                         parameterSetSizeOut: nil, parameterSetCountOut: &count, nalUnitHeaderLengthOut: nil)
      for i in 0..<count {
        var pointer: UnsafePointer<UInt8>?
        var size = 0
        if CMVideoFormatDescriptionGetH264ParameterSetAtIndex(format, parameterSetIndex: i, parameterSetPointerOut: &pointer,
                                                              parameterSetSizeOut: &size, parameterSetCountOut: nil, nalUnitHeaderLengthOut: nil) == noErr,
           let p = pointer {
          out.append(startCode)
          out.append(p, count: size)
        }
      }
    }
    var length = 0
    var pointer: UnsafeMutablePointer<Int8>?
    guard CMBlockBufferGetDataPointer(dataBuffer, atOffset: 0, lengthAtOffsetOut: nil, totalLengthOut: &length, dataPointerOut: &pointer) == noErr,
          let base = pointer else { return }
    var offset = 0
    while offset + 4 <= length {
      let nalLength = Int(UInt32(bigEndian: UnsafeRawPointer(base + offset).loadUnaligned(as: UInt32.self)))
      offset += 4
      guard nalLength > 0, offset + nalLength <= length else { break }
      out.append(startCode)
      out.append(UnsafeRawPointer(base + offset).assumingMemoryBound(to: UInt8.self), count: nalLength)
      offset += nalLength
    }
    let pts = CMSampleBufferGetPresentationTimeStamp(sample)
    let ts = Int64((Double(pts.value) / Double(pts.timescale) * 1000).rounded())
    lock.lock()
    pending.append(Chunk(ts: ts, data: out))
    lock.unlock()
  }

  /// The frame flipped left-right, so the server gets the un-mirrored face a photo would show.
  private func mirrored(_ src: CVPixelBuffer) -> CVPixelBuffer? {
    if mirrorBuffer == nil {
      var b: CVPixelBuffer?
      let attrs: [CFString: Any] = [kCVPixelBufferIOSurfacePropertiesKey: [:]]
      CVPixelBufferCreate(nil, width, height, kCVPixelFormatType_32BGRA, attrs as CFDictionary, &b)
      mirrorBuffer = b
    }
    guard let dst = mirrorBuffer else { return nil }
    CVPixelBufferLockBaseAddress(src, .readOnly)
    CVPixelBufferLockBaseAddress(dst, [])
    defer {
      CVPixelBufferUnlockBaseAddress(src, .readOnly)
      CVPixelBufferUnlockBaseAddress(dst, [])
    }
    guard let s = CVPixelBufferGetBaseAddress(src), let d = CVPixelBufferGetBaseAddress(dst) else { return nil }
    var sBuf = vImage_Buffer(data: s, height: vImagePixelCount(height), width: vImagePixelCount(width), rowBytes: CVPixelBufferGetBytesPerRow(src))
    var dBuf = vImage_Buffer(data: d, height: vImagePixelCount(height), width: vImagePixelCount(width), rowBytes: CVPixelBufferGetBytesPerRow(dst))
    return vImageHorizontalReflect_ARGB8888(&sBuf, &dBuf, vImage_Flags(kvImageNoFlags)) == kvImageNoError ? dst : nil
  }
}
